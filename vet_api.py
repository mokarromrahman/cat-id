"""Vet visit endpoints (used by the app's Vet tab). Included by app.py.

All of them check API_KEY in the X-API-Key header. `user` is the app's "who am I" name; a
missing or unknown user is recorded as the system user. Unlike /litterbox, these need the
database: if it's down they answer 503 and nothing is saved (the app shows the error).

POST   /vet_visit                {"user", "visits": [visit, ...]}  one visit, or two (one per
                                 cat, for "both"); saved all or nothing -> {"visits": [...]}
GET    /vet_visit                active visits, newest first; ?include_deleted=true adds the
                                 soft-deleted ones -> {"visits": [...]}
PATCH  /vet_visit/{id}           {"user", any visit fields} -> the updated visit
DELETE /vet_visit/{id}?user=     soft delete (sets deleted_on) -> the visit
POST   /vet_visit/{id}/restore?user=   undo a soft delete -> the visit

A visit: {"cat": "Litten" | "Shinx" | null, "visit_date": "2026-11-11",
          "appointment_time": "14:30" | null, "doctor", "clinic", "notes",
          "reason": ["checkup", ...], "weight_kg", "cost", "follow_up_date"}
Replies also carry id, reporter, deleted_on, created_on, modified_on, modified_by.
A missing or blank clinic is stored as "unknown".
"""
import os
from datetime import date, time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

import db

API_KEY = os.environ.get("API_KEY", "")
router = APIRouter()

CatName = Literal["Litten", "Shinx"]
Reason = Literal["checkup", "shots", "emergency", "food pickup", "medication pickup", "other"]


def _blank_to_none(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class VisitFields(BaseModel):
    cat: CatName | None = None
    visit_date: date | None = None
    appointment_time: time | None = None
    doctor: str | None = None
    clinic: str | None = None
    notes: str | None = None
    reason: list[Reason] | None = Field(None, min_length=1)
    weight_kg: Decimal | None = Field(None, gt=0, max_digits=5, decimal_places=2)
    cost: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    follow_up_date: date | None = None

    @field_validator("doctor", "clinic", "notes", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)


class NewVisit(VisitFields):
    visit_date: date
    reason: list[Reason] = Field(min_length=1)


class NewVisits(BaseModel):
    user: str | None = None
    visits: list[NewVisit] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def both_means_one_per_cat(self):
        if len(self.visits) == 2 and {v.cat for v in self.visits} != {"Litten", "Shinx"}:
            raise ValueError("two visits must be one for Litten and one for Shinx")
        return self


class VisitChanges(VisitFields):
    user: str | None = None


def _check_key(key: str | None):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")


def _session():
    if db.is_down():
        raise HTTPException(503, "database unavailable, nothing was saved")
    return db.SessionLocal()


def _db_error(e):
    db._mark_down(e)
    return HTTPException(503, f"database unavailable, nothing was saved ({type(e).__name__})")


def _rejected(e):
    """A database rule refused the change; nothing was saved (all or nothing)."""
    reason = str(getattr(e, "orig", e)).splitlines()[0]
    return HTTPException(400, f"nothing was saved: the database rejected it ({reason})")


def _num(v):
    return float(v) if v is not None else None


def _iso(v):
    return v.isoformat() if v is not None else None


def _visits(session, *where):
    """Visit dicts for the rows matching `where`, newest first."""
    reporter, modifier = aliased(db.AppUser), aliased(db.AppUser)
    q = (select(db.VetVisit, db.Cat.name, reporter.name, modifier.name)
         .outerjoin(db.Cat, db.Cat.id == db.VetVisit.cat_id)
         .join(reporter, reporter.id == db.VetVisit.reporter_id)
         .join(modifier, modifier.id == db.VetVisit.modified_by)
         .where(*where)
         .order_by(db.VetVisit.visit_date.desc(),
                   db.VetVisit.appointment_time.desc().nulls_last(), db.VetVisit.id.desc()))
    return [{
        "id": v.id, "cat": cat, "visit_date": _iso(v.visit_date),
        "appointment_time": v.appointment_time.strftime("%H:%M") if v.appointment_time else None,
        "doctor": v.doctor, "clinic": v.clinic, "notes": v.notes, "reason": v.reason,
        "weight_kg": _num(v.weight_kg), "cost": _num(v.cost),
        "follow_up_date": _iso(v.follow_up_date), "reporter": rep,
        "deleted_on": _iso(v.deleted_on), "created_on": _iso(v.created_on),
        "modified_on": _iso(v.modified_on), "modified_by": mod,
    } for v, cat, rep, mod in session.execute(q)]


def _cat_id(session, name):
    return session.scalar(select(db.Cat.id).where(db.Cat.name == name)) if name else None


def _get(session, visit_id) -> db.VetVisit:
    v = session.get(db.VetVisit, visit_id)
    if v is None:
        raise HTTPException(404, "no such visit")
    return v


def _one(session, visit_id):
    return _visits(session, db.VetVisit.id == visit_id)[0]


@router.post("/vet_visit")
def create_visits(body: NewVisits, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    try:
        with _session() as session, session.begin():
            uid = db.user_id(session, body.user)
            rows = []
            for v in body.visits:
                fields = v.model_dump(exclude={"cat", "clinic"})
                row = db.VetVisit(**fields, cat_id=_cat_id(session, v.cat), reporter_id=uid,
                                  modified_by=uid, clinic=v.clinic or "unknown")
                session.add(row)
                rows.append(row)
            session.flush()
            ids = [r.id for r in rows]
            return {"visits": [_one(session, i) for i in ids]}
    except HTTPException:
        raise
    except IntegrityError as e:
        raise _rejected(e)
    except db.OperationalError as e:
        raise _db_error(e)


@router.get("/vet_visit")
def list_visits(include_deleted: bool = False, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    try:
        with _session() as session:
            where = [] if include_deleted else [db.VetVisit.deleted_on.is_(None)]
            return {"visits": _visits(session, *where)}
    except HTTPException:
        raise
    except IntegrityError as e:
        raise _rejected(e)
    except db.OperationalError as e:
        raise _db_error(e)


@router.patch("/vet_visit/{visit_id}")
def edit_visit(visit_id: int, body: VisitChanges, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    changes = body.model_dump(exclude_unset=True, exclude={"user"})
    for required in ("visit_date", "reason"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} can't be empty")
    try:
        with _session() as session, session.begin():
            v = _get(session, visit_id)
            if v.deleted_on is not None:
                raise HTTPException(409, "this visit is deleted; restore it before editing")
            if "cat" in changes:
                v.cat_id = _cat_id(session, changes.pop("cat"))
            if "clinic" in changes:
                changes["clinic"] = changes["clinic"] or "unknown"
            for k, val in changes.items():
                setattr(v, k, val)
            v.modified_by = db.user_id(session, body.user)
            session.flush()
            return _one(session, visit_id)
    except HTTPException:
        raise
    except IntegrityError as e:
        raise _rejected(e)
    except db.OperationalError as e:
        raise _db_error(e)


def _set_deleted(visit_id, user, deleted, key):
    _check_key(key)
    try:
        with _session() as session, session.begin():
            v = _get(session, visit_id)
            if (v.deleted_on is not None) == deleted:
                raise HTTPException(409, "already deleted" if deleted else "this visit isn't deleted")
            v.deleted_on = db.utcnow() if deleted else None
            v.modified_by = db.user_id(session, user)
            session.flush()
            return _one(session, visit_id)
    except HTTPException:
        raise
    except IntegrityError as e:
        raise _rejected(e)
    except db.OperationalError as e:
        raise _db_error(e)


@router.delete("/vet_visit/{visit_id}")
def delete_visit(visit_id: int, user: str | None = None, x_api_key: str | None = Header(None)):
    return _set_deleted(visit_id, user, True, x_api_key)


@router.post("/vet_visit/{visit_id}/restore")
def restore_visit(visit_id: int, user: str | None = None, x_api_key: str | None = Header(None)):
    return _set_deleted(visit_id, user, False, x_api_key)
