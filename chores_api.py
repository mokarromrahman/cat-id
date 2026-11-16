"""Chore endpoints (used by the app's Chores page). Included by app.py.

All of them check API_KEY in the X-API-Key header. `user` is the app's "who am I" name; a
missing or unknown user is recorded as the system user. Like /vet_visit these need the
database: if it's down they answer 503 and nothing is saved. No Discord posts.

GET    /chores                   active chores, in table order, each with its status, plus the
                                 people who can be picked as having done one:
                                 ?include_inactive=true adds the hidden chores
                                 -> {"chores": [chore, ...], "people": ["Ashley", "Mac", ...]}
POST   /chores                   {"user", "label_name", "warning_threshold_days" (null = no
                                 reminder), optional "name"} -> the chore. `name` (the code)
                                 defaults to label_name in snake_case ("Clean Fridge" ->
                                 clean_fridge); 409 if a chore (hidden ones too) has it
PATCH  /chores/{id}              {"user", any of label_name, warning_threshold_days, active}
                                 -> the chore. The code (`name`) never changes. active=false
                                 hides it (a chore with events can't be deleted)
GET    /chore_events             newest first. ?chore=<name> (left out = all chores),
                                 include_deleted=true, limit=1..200 (default 50),
                                 before=<next> -> {"events": [event, ...], "next": ... | null}
POST   /chore_events             {"user", "chore" (a chore name), optional "event_time" (ISO
                                 8601 with an offset; missing = now; not in the future),
                                 "done_by": ["Ashley", ...] (people; empty or missing = not
                                 recorded), "notes"} -> the event
PATCH  /chore_events/{id}        {"user", any of chore, event_time, done_by, notes} -> the event
DELETE /chore_events/{id}?user=  soft delete (sets deleted_on) -> the event
POST   /chore_events/{id}/restore?user=   undo a soft delete -> the event

A chore: {"id", "name", "label_name", "warning_threshold_days", "active",
          "last_done" (UTC, null if never), "last_done_by": [names], "due_at" (UTC, null
          without a threshold or if never done), "overdue"}.
          Overdue = has a threshold and either was never done or more than
          warning_threshold_days x 24 h have passed since it was last done (see db.chore_rows).
An event: {"id", "chore", "chore_label", "event_timestamp" (UTC), "done_by": [names],
           "reporter", "notes", "deleted_on", "created_on", "modified_on", "modified_by"}.
"""
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

import db
from events_api import _cursor, _parse_cursor

API_KEY = os.environ.get("API_KEY", "")
# An event_time may be this far ahead of the server's clock (phone clock drift), as in app.py.
CLOCK_SLACK = timedelta(minutes=5)
router = APIRouter()


def _blank_to_none(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def code_for(label: str) -> str:
    """"Cat Food Pickup" -> "cat_food_pickup"."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


class NewChore(BaseModel):
    user: str | None = None
    label_name: str = Field(min_length=1, max_length=60)
    name: str | None = Field(None, max_length=60, pattern=r"^[a-z0-9_]+$")
    warning_threshold_days: int | None = Field(None, ge=1, le=3650)

    @field_validator("label_name", "name", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)


class ChoreChanges(BaseModel):
    user: str | None = None
    label_name: str | None = Field(None, min_length=1, max_length=60)
    warning_threshold_days: int | None = Field(None, ge=1, le=3650)
    active: bool | None = None

    @field_validator("label_name", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)


class EventFields(BaseModel):
    chore: str | None = None
    event_time: datetime | None = None
    done_by: list[str] | None = Field(None, max_length=20)
    notes: str | None = None

    @field_validator("notes", "chore", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)

    @field_validator("event_time")
    @classmethod
    def _past_with_offset(cls, v):
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("needs a UTC offset (e.g. ...Z or ...-06:00)")
        if v > db.utcnow() + CLOCK_SLACK:
            raise ValueError("can't be in the future")
        return min(v.astimezone(timezone.utc), db.utcnow())


class NewEvent(EventFields):
    user: str | None = None
    chore: str


class EventChanges(EventFields):
    user: str | None = None


def _check_key(key: str | None):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")


def _session():
    if db.is_down():
        raise HTTPException(503, "database unavailable, nothing was saved")
    return db.SessionLocal()


def _run(fn):
    """fn() inside the shared error handling: 503 when the database is down, 400 when one
    of its rules refuses the change (nothing is saved either way)."""
    try:
        return fn()
    except HTTPException:
        raise
    except IntegrityError as e:
        reason = str(getattr(e, "orig", e)).splitlines()[0]
        raise HTTPException(400, f"nothing was saved: the database rejected it ({reason})")
    except db.OperationalError as e:
        db._mark_down(e)
        raise HTTPException(503, f"database unavailable, nothing was saved ({type(e).__name__})")


def _iso(v):
    return v.isoformat() if v is not None else None


# ---------- chores ----------

def people(session) -> list[str]:
    """Names that can be picked as having done a chore (app_user.human), alphabetical."""
    return list(session.scalars(
        select(db.AppUser.name).where(db.AppUser.human).order_by(db.AppUser.name)))


def _chore(session, chore_id) -> dict:
    for c in db.chore_rows(session, include_inactive=True):
        if c["id"] == chore_id:
            return c
    raise HTTPException(404, "no such chore")


@router.get("/chores")
def list_chores(include_inactive: bool = False, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session:
            return {"chores": db.chore_rows(session, include_inactive),
                    "people": people(session)}
    return _run(go)


@router.post("/chores")
def create_chore(body: NewChore, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    code = body.name or code_for(body.label_name)
    if not code:
        raise HTTPException(422, "label name needs at least one letter or digit")

    def go():
        with _session() as session, session.begin():
            existing = session.scalar(select(db.Chore).where(db.Chore.name == code))
            if existing is not None:
                hidden = "" if existing.active else " (hidden: show hidden chores to bring it back)"
                raise HTTPException(409, f"there's already a chore {existing.label_name!r}{hidden}")
            uid = db.user_id(session, body.user)
            row = db.Chore(name=code, label_name=body.label_name,
                           warning_threshold_days=body.warning_threshold_days, modified_by=uid)
            session.add(row)
            session.flush()
            return _chore(session, row.id)
    return _run(go)


@router.patch("/chores/{chore_id}")
def edit_chore(chore_id: int, body: ChoreChanges, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    changes = body.model_dump(exclude_unset=True, exclude={"user"})
    for required in ("label_name", "active"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required.replace('_', ' ')} can't be empty")

    def go():
        with _session() as session, session.begin():
            c = session.get(db.Chore, chore_id)
            if c is None:
                raise HTTPException(404, "no such chore")
            for k, v in changes.items():
                setattr(c, k, v)
            c.modified_by = db.user_id(session, body.user)
            session.flush()
            return _chore(session, chore_id)
    return _run(go)


# ---------- chore events ----------

def _events(session, *where, limit: int | None = None):
    """Event dicts for the rows matching `where`, newest first."""
    reporter, modifier = aliased(db.AppUser), aliased(db.AppUser)
    q = (select(db.ChoreEvent, db.Chore.name, db.Chore.label_name, reporter.name, modifier.name)
         .join(db.Chore, db.Chore.id == db.ChoreEvent.chore_id)
         .join(reporter, reporter.id == db.ChoreEvent.reporter_id)
         .join(modifier, modifier.id == db.ChoreEvent.modified_by)
         .where(*where)
         .order_by(db.ChoreEvent.event_timestamp.desc(), db.ChoreEvent.id.desc()))
    if limit is not None:
        q = q.limit(limit)
    rows = session.execute(q).all()
    doers = db.chore_doers(session, [e.id for e, *_ in rows])
    return [{
        "id": e.id, "chore": name, "chore_label": label,
        "event_timestamp": db._iso(e.event_timestamp), "done_by": doers.get(e.id, []),
        "reporter": rep, "notes": e.notes, "deleted_on": _iso(e.deleted_on),
        "created_on": _iso(e.created_on), "modified_on": _iso(e.modified_on), "modified_by": mod,
    } for e, name, label, rep, mod in rows]


def _get_event(session, event_id) -> db.ChoreEvent:
    e = session.get(db.ChoreEvent, event_id)
    if e is None:
        raise HTTPException(404, "no such chore event")
    return e


def _one(session, event_id):
    return _events(session, db.ChoreEvent.id == event_id)[0]


def _chore_id(session, name: str) -> int:
    found = session.scalar(select(db.Chore.id).where(db.Chore.name == name))
    if found is None:
        raise HTTPException(400, f"unknown chore {name!r}")
    return found


def _set_doers(session, event_id: int, names: list[str], uid: int):
    """Replace who did event `event_id`. Each name must be a person (app_user.human);
    repeats are ignored. 400 for anyone else, and nothing is saved."""
    wanted = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    ids = dict(session.execute(select(db.AppUser.name, db.AppUser.id).where(
        db.AppUser.name.in_(wanted), db.AppUser.human)).tuples().all()) if wanted else {}
    unknown = [n for n in wanted if n not in ids]
    if unknown:
        raise HTTPException(400, f"not a person who can do chores: {', '.join(unknown)} "
                                 f"(known: {', '.join(people(session))})")
    session.execute(delete(db.ChoreEventDoer).where(db.ChoreEventDoer.chore_event_id == event_id))
    for n in wanted:
        session.add(db.ChoreEventDoer(chore_event_id=event_id, app_user_id=ids[n], modified_by=uid))


@router.get("/chore_events")
def list_events(chore: str | None = None, include_deleted: bool = False,
                limit: int = Query(50, ge=1, le=200), before: str | None = None,
                x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session:
            where = [] if include_deleted else [db.ChoreEvent.deleted_on.is_(None)]
            if chore:
                where.append(db.ChoreEvent.chore_id == _chore_id(session, chore))
            if before:
                ts, eid = _parse_cursor(before)
                where.append(tuple_(db.ChoreEvent.event_timestamp, db.ChoreEvent.id) < (ts, eid))
            events = _events(session, *where, limit=limit + 1)
            more = len(events) > limit
            events = events[:limit]
            nxt = (_cursor(datetime.fromisoformat(events[-1]["event_timestamp"]), events[-1]["id"])
                   if more else None)
            return {"events": events, "next": nxt}
    return _run(go)


@router.post("/chore_events")
def create_event(body: NewEvent, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            uid = db.user_id(session, body.user)
            row = db.ChoreEvent(chore_id=_chore_id(session, body.chore),
                                event_timestamp=body.event_time or db.utcnow(),
                                reporter_id=uid, notes=body.notes, modified_by=uid)
            session.add(row)
            session.flush()
            _set_doers(session, row.id, body.done_by or [], uid)
            session.flush()
            return _one(session, row.id)
    return _run(go)


@router.patch("/chore_events/{event_id}")
def edit_event(event_id: int, body: EventChanges, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    changes = body.model_dump(exclude_unset=True, exclude={"user"})
    for required in ("chore", "event_time"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required.replace('_', ' ')} can't be empty")

    def go():
        with _session() as session, session.begin():
            e = _get_event(session, event_id)
            if e.deleted_on is not None:
                raise HTTPException(409, "this chore event is deleted; restore it before editing")
            uid = db.user_id(session, body.user)
            if "chore" in changes:
                e.chore_id = _chore_id(session, changes["chore"])
            if "event_time" in changes:
                e.event_timestamp = changes["event_time"]
            if "notes" in changes:
                e.notes = changes["notes"]
            if "done_by" in changes:
                _set_doers(session, e.id, changes["done_by"] or [], uid)
            e.modified_by = uid
            session.flush()
            return _one(session, event_id)
    return _run(go)


def _set_deleted(event_id, user, deleted, key):
    _check_key(key)

    def go():
        with _session() as session, session.begin():
            e = _get_event(session, event_id)
            if (e.deleted_on is not None) == deleted:
                raise HTTPException(409, "already deleted" if deleted else "this chore event isn't deleted")
            e.deleted_on = db.utcnow() if deleted else None
            e.modified_by = db.user_id(session, user)
            session.flush()
            return _one(session, event_id)
    return _run(go)


@router.delete("/chore_events/{event_id}")
def delete_event(event_id: int, user: str | None = None, x_api_key: str | None = Header(None)):
    return _set_deleted(event_id, user, True, x_api_key)


@router.post("/chore_events/{event_id}/restore")
def restore_event(event_id: int, user: str | None = None, x_api_key: str | None = Header(None)):
    return _set_deleted(event_id, user, False, x_api_key)
