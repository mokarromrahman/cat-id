"""Chore endpoints (used by the app's Chores page). Included by app.py.

All of them check API_KEY in the X-API-Key header. `user` is the app's "who am I" name; a
missing or unknown user is recorded as the system user. Like /vet_visit these need the
database: if it's down they answer 503 and nothing is saved. Requests, Dones,
cancellations, starts and stops post to CHORES_DISCORD_WEBHOOK_URL after the response
(chore_discord.py; skipped when it isn't set).

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
                                 recorded), "notes", "started_at" (when it was started; ISO
                                 8601 with an offset, not after event_time; missing = from
                                 the chore's start if it's in progress, else not known; null
                                 = not known)} -> the event. Closes the chore's open request
                                 and ends its start ("done"), if any; posts "done" to Discord
PATCH  /chore_events/{id}        {"user", any of chore, event_time, done_by, notes, started_at
                                 (null clears)} -> the event. Start after done: 400
DELETE /chore_events/{id}?user=  soft delete (sets deleted_on) -> the event. If this Done
                                 closed a request or ended a start, they open again (unless
                                 the chore already has another open one)
POST   /chore_events/{id}/restore?user=   undo a soft delete -> the event (closes the request
                                 and ends the start it reopened, if they're still open)
GET    /chore_starts             newest first. ?chore=<name>, status=in_progress|done|stopped
                                 (left out = all), limit=1..200 (default 50), before=<next>
                                 -> {"starts": [start, ...], "next": ... | null}
POST   /chore_starts             someone is doing a chore now: {"user", "chore", optional
                                 "doers": [people] (empty = not recorded), "started_at" (ISO
                                 8601 with offset; missing = now; not in the future), "notes"}
                                 -> the start. 409 if the chore is already in progress.
                                 Posts it to Discord
PATCH  /chore_starts/{id}        {"user", any of doers (join / take over), started_at, notes}
                                 -> the start; in-progress only (409 otherwise). No Discord
POST   /chore_starts/{id}/stop?user=  gave up without finishing -> the start; in-progress
                                 only (409 otherwise). Anyone can stop it. Posts it to Discord
GET    /chore_requests           newest first. ?chore=<name>, status=open|done|cancelled
                                 (left out = all), limit=1..200 (default 50), before=<next>
                                 -> {"requests": [request, ...], "next": ... | null}
POST   /chore_requests           mark a chore as needed: {"user", "chore", optional "notes",
                                 "quantity" (> 0), "unit" (free text, e.g. bags),
                                 "needed_by" (YYYY-MM-DD, an Edmonton day, not in the past)}
                                 -> the request. 409 if the chore already has an open one.
                                 Posts it to Discord
PATCH  /chore_requests/{id}      {"user", any of notes, quantity, unit, needed_by (null clears)}
                                 -> the request; open requests only (409 otherwise). Edits
                                 the Discord message
POST   /chore_requests/{id}/cancel?user=  -> the request; open only (409 otherwise). Edits
                                 the Discord message and posts that it was cancelled

A chore: {"id", "name", "label_name", "warning_threshold_days", "active",
          "last_done" (UTC, null if never), "last_done_by": [names], "due_at" (UTC, null
          without a threshold or if never done), "overdue", "request" (the open request, or
          null), "in_progress" (the start in progress, or null)}.
          Overdue = has a threshold and either was never done or more than
          warning_threshold_days x 24 h have passed since it was last done, or the open
          request's needed_by day (Edmonton) is over (see db.chore_rows).
An event: {"id", "chore", "chore_label", "event_timestamp" (UTC), "done_by": [names],
           "reporter", "notes", "started_on" (UTC or null), "took_seconds" (event_timestamp
           - started_on, or null), "deleted_on", "created_on", "modified_on", "modified_by"}.
A start: {"id", "chore_id", "chore", "chore_label", "started_on" (UTC), "doers": [names],
          "reporter", "notes", "status" (in_progress/done/stopped), "ended_on", "ended_by",
          "chore_event_id" (the Done that ended it)}.
At most one start in progress per chore. The time a Done took counts from that start
(whoever joined later).
A request: {"id", "chore_id", "chore", "chore_label", "requested_on" (UTC), "requested_by",
            "notes", "quantity" (number or null), "unit", "needed_by" (YYYY-MM-DD or null),
            "status" (open/done/cancelled), "done_on", "chore_event_id" (the Done that closed
            it), "done_by" (that Done's people), "cancelled_on", "closed_by" (who recorded the
            Done or cancelled it), "overdue" (open and past needed_by)}.
At most one open request per chore. A request is closed only by a Done or Cancel (a vet
visit doesn't close it).
"""
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

import chore_discord
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


def _past_with_offset(v):
    """An ISO time with a UTC offset that isn't in the future (beyond CLOCK_SLACK), in UTC."""
    if v is None:
        return v
    if v.tzinfo is None:
        raise ValueError("needs a UTC offset (e.g. ...Z or ...-06:00)")
    if v > db.utcnow() + CLOCK_SLACK:
        raise ValueError("can't be in the future")
    return min(v.astimezone(timezone.utc), db.utcnow())


class EventFields(BaseModel):
    chore: str | None = None
    event_time: datetime | None = None
    done_by: list[str] | None = Field(None, max_length=20)
    notes: str | None = None
    started_at: datetime | None = None

    @field_validator("notes", "chore", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)

    @field_validator("event_time", "started_at")
    @classmethod
    def _times(cls, v):
        return _past_with_offset(v)


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
        "reporter": rep, "notes": e.notes, "started_on": db._iso(e.started_on),
        "took_seconds": (int((e.event_timestamp - e.started_on).total_seconds())
                         if e.started_on else None),
        "deleted_on": _iso(e.deleted_on),
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


def _person_ids(session, names: list[str]) -> list[int]:
    """app_user ids for `names`, each of which must be a person (app_user.human); repeats
    are ignored. 400 for anyone else, and nothing is saved."""
    wanted = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    ids = dict(session.execute(select(db.AppUser.name, db.AppUser.id).where(
        db.AppUser.name.in_(wanted), db.AppUser.human)).tuples().all()) if wanted else {}
    unknown = [n for n in wanted if n not in ids]
    if unknown:
        raise HTTPException(400, f"not a person who can do chores: {', '.join(unknown)} "
                                 f"(known: {', '.join(people(session))})")
    return [ids[n] for n in wanted]


def _set_doers(session, event_id: int, names: list[str], uid: int):
    """Replace who did event `event_id` (see _person_ids)."""
    ids = _person_ids(session, names)
    session.execute(delete(db.ChoreEventDoer).where(db.ChoreEventDoer.chore_event_id == event_id))
    for i in ids:
        session.add(db.ChoreEventDoer(chore_event_id=event_id, app_user_id=i, modified_by=uid))


def _set_start_doers(session, start_id: int, names: list[str], uid: int):
    """Replace who is doing start `start_id` (see _person_ids)."""
    ids = _person_ids(session, names)
    session.execute(delete(db.ChoreStartDoer).where(db.ChoreStartDoer.chore_start_id == start_id))
    for i in ids:
        session.add(db.ChoreStartDoer(chore_start_id=start_id, app_user_id=i, modified_by=uid))


def _check_order(started_on, done_on):
    if started_on is not None and started_on > done_on:
        raise HTTPException(400, "the start time is after the done time; nothing was saved")


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
def create_event(body: NewEvent, tasks: BackgroundTasks, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            uid = db.user_id(session, body.user)
            chore_id = _chore_id(session, body.chore)
            done_at = body.event_time or db.utcnow()
            start = session.scalar(select(db.ChoreStart).where(
                db.ChoreStart.chore_id == chore_id, db.START_OPEN))
            # The time it took counts from the start in progress, unless one was sent.
            started_on = (body.started_at if "started_at" in body.model_fields_set
                          else start.started_on if start is not None else None)
            _check_order(started_on, done_at)
            row = db.ChoreEvent(chore_id=chore_id, event_timestamp=done_at, started_on=started_on,
                                reporter_id=uid, notes=body.notes, modified_by=uid)
            session.add(row)
            session.flush()
            _set_doers(session, row.id, body.done_by or [], uid)
            if start is not None:
                start.ended_on, start.end_reason, start.chore_event_id = db.utcnow(), "done", row.id
                start.ended_by = start.modified_by = uid
            # A Done closes the chore's open request, if it has one.
            req = session.scalar(select(db.ChoreRequest).where(
                db.ChoreRequest.chore_id == chore_id, db.REQUEST_OPEN))
            if req is not None:
                req.done_on, req.chore_event_id = db.utcnow(), row.id
                req.closed_by = req.modified_by = uid
            session.flush()
            event = _one(session, row.id)
            closed = _request(session, req.id) if req is not None else None
            ended = _start(session, start.id) if start is not None else None
        tasks.add_task(chore_discord.done, event, closed, ended)
        return event
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
            if "started_at" in changes:
                e.started_on = changes["started_at"]
            _check_order(e.started_on, e.event_timestamp)
            if "notes" in changes:
                e.notes = changes["notes"]
            if "done_by" in changes:
                _set_doers(session, e.id, changes["done_by"] or [], uid)
            e.modified_by = uid
            session.flush()
            return _one(session, event_id)
    return _run(go)


def _set_deleted(event_id, user, deleted, key, tasks: BackgroundTasks):
    """Soft delete or restore a Done. Deleting the Done that closed a request reopens the
    request (unless the chore has a newer open one); restoring it closes it again. The same
    for the start it ended (back in progress, then ended again)."""
    _check_key(key)

    def go():
        with _session() as session, session.begin():
            e = _get_event(session, event_id)
            if (e.deleted_on is not None) == deleted:
                raise HTTPException(409, "already deleted" if deleted else "this chore event isn't deleted")
            uid = db.user_id(session, user)
            e.deleted_on = db.utcnow() if deleted else None
            e.modified_by = uid
            req = session.scalar(select(db.ChoreRequest).where(
                db.ChoreRequest.chore_event_id == event_id))
            changed = None
            if req is not None:
                is_open = req.done_on is None and req.cancelled_on is None
                other_open = session.scalar(select(db.ChoreRequest.id).where(
                    db.ChoreRequest.chore_id == req.chore_id, db.REQUEST_OPEN,
                    db.ChoreRequest.id != req.id))
                if deleted and req.done_on is not None and other_open is None:
                    req.done_on = req.closed_by = None
                    req.modified_by = uid
                    changed = "reopened"
                elif not deleted and is_open:
                    req.done_on, req.closed_by, req.modified_by = db.utcnow(), e.reporter_id, uid
                    changed = "closed"
            start = session.scalar(select(db.ChoreStart).where(
                db.ChoreStart.chore_event_id == event_id))
            start_changed = False
            if start is not None:
                other = session.scalar(select(db.ChoreStart.id).where(
                    db.ChoreStart.chore_id == start.chore_id, db.START_OPEN,
                    db.ChoreStart.id != start.id))
                if deleted and start.end_reason == "done" and other is None:
                    start.ended_on = start.end_reason = start.ended_by = None
                    start.modified_by, start_changed = uid, True
                elif not deleted and start.ended_on is None and other is None:
                    start.ended_on, start.end_reason = db.utcnow(), "done"
                    start.ended_by, start.modified_by, start_changed = e.reporter_id, uid, True
            session.flush()
            event = _one(session, event_id)
            r = _request(session, req.id) if changed else None
            s = _start(session, start.id) if start_changed else None
        if s is not None:
            tasks.add_task(chore_discord.start_edited, s, event)
        if changed == "reopened":
            tasks.add_task(chore_discord.reopened, r, user)
        elif changed == "closed":
            tasks.add_task(chore_discord.request_edited, r)
        return event
    return _run(go)


@router.delete("/chore_events/{event_id}")
def delete_event(event_id: int, tasks: BackgroundTasks, user: str | None = None,
                 x_api_key: str | None = Header(None)):
    return _set_deleted(event_id, user, True, x_api_key, tasks)


@router.post("/chore_events/{event_id}/restore")
def restore_event(event_id: int, tasks: BackgroundTasks, user: str | None = None,
                  x_api_key: str | None = Header(None)):
    return _set_deleted(event_id, user, False, x_api_key, tasks)


# ---------- chore requests ("this needs doing") ----------

class RequestFields(BaseModel):
    notes: str | None = None
    quantity: float | None = Field(None, gt=0, le=99_999_999)
    unit: str | None = Field(None, max_length=30)
    needed_by: date | None = None

    @field_validator("notes", "unit", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)

    @field_validator("needed_by")
    @classmethod
    def _not_past(cls, v):
        if v is not None and v < datetime.now(db.EDMONTON).date():
            raise ValueError("can't be in the past")
        return v


class NewRequest(RequestFields):
    user: str | None = None
    chore: str


class RequestChanges(RequestFields):
    user: str | None = None


def _request(session, request_id) -> dict:
    found = db.chore_requests(session, db.ChoreRequest.id == request_id)
    if not found:
        raise HTTPException(404, "no such chore request")
    return found[0]


def _open_request(session, request_id) -> db.ChoreRequest:
    r = session.get(db.ChoreRequest, request_id)
    if r is None:
        raise HTTPException(404, "no such chore request")
    if r.done_on is not None or r.cancelled_on is not None:
        raise HTTPException(409, "this request is already " + ("done" if r.done_on else "cancelled"))
    return r


@router.get("/chore_requests")
def list_requests(chore: str | None = None,
                  status: Literal["open", "done", "cancelled"] | None = None,
                  limit: int = Query(50, ge=1, le=200), before: str | None = None,
                  x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    R = db.ChoreRequest

    def go():
        with _session() as session:
            where = []
            if chore:
                where.append(R.chore_id == _chore_id(session, chore))
            if status == "open":
                where.append(db.REQUEST_OPEN)
            elif status == "done":
                where.append(R.done_on.is_not(None))
            elif status == "cancelled":
                where.append(R.cancelled_on.is_not(None))
            if before:
                ts, rid = _parse_cursor(before)
                where.append(tuple_(R.requested_on, R.id) < (ts, rid))
            found = db.chore_requests(session, *where, limit=limit + 1)
            more = len(found) > limit
            found = found[:limit]
            nxt = (_cursor(datetime.fromisoformat(found[-1]["requested_on"]), found[-1]["id"])
                   if more else None)
            return {"requests": found, "next": nxt}
    return _run(go)


@router.post("/chore_requests")
def create_request(body: NewRequest, tasks: BackgroundTasks, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            chore_id = _chore_id(session, body.chore)
            if session.scalar(select(db.ChoreRequest.id).where(
                    db.ChoreRequest.chore_id == chore_id, db.REQUEST_OPEN)) is not None:
                raise HTTPException(409, "this chore is already marked as needed; edit that request")
            uid = db.user_id(session, body.user)
            row = db.ChoreRequest(chore_id=chore_id, reporter_id=uid, notes=body.notes,
                                  quantity=body.quantity, unit=body.unit,
                                  needed_by=body.needed_by, modified_by=uid)
            session.add(row)
            session.flush()
            r = _request(session, row.id)
        tasks.add_task(chore_discord.requested, r)
        return r
    return _run(go)


@router.patch("/chore_requests/{request_id}")
def edit_request(request_id: int, body: RequestChanges, tasks: BackgroundTasks,
                 x_api_key: str | None = Header(None)):
    """Change an open request's notes, quantity, unit or needed_by (null clears one)."""
    _check_key(x_api_key)
    changes = body.model_dump(exclude_unset=True, exclude={"user"})

    def go():
        with _session() as session, session.begin():
            row = _open_request(session, request_id)
            for k, v in changes.items():
                setattr(row, k, v)
            row.modified_by = db.user_id(session, body.user)
            session.flush()
            r = _request(session, request_id)
        tasks.add_task(chore_discord.request_edited, r)
        return r
    return _run(go)


@router.post("/chore_requests/{request_id}/cancel")
def cancel_request(request_id: int, tasks: BackgroundTasks, user: str | None = None,
                   x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            row = _open_request(session, request_id)
            uid = db.user_id(session, user)
            row.cancelled_on, row.closed_by, row.modified_by = db.utcnow(), uid, uid
            session.flush()
            r = _request(session, request_id)
        tasks.add_task(chore_discord.cancelled, r)
        return r
    return _run(go)


# ---------- chore starts ("doing it now") ----------

class StartFields(BaseModel):
    doers: list[str] | None = Field(None, max_length=20)
    started_at: datetime | None = None
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _strip(cls, v):
        return _blank_to_none(v)

    @field_validator("started_at")
    @classmethod
    def _time(cls, v):
        return _past_with_offset(v)


class NewStart(StartFields):
    user: str | None = None
    chore: str


class StartChanges(StartFields):
    user: str | None = None


def _start(session, start_id) -> dict:
    found = db.chore_starts(session, db.ChoreStart.id == start_id)
    if not found:
        raise HTTPException(404, "no such chore start")
    return found[0]


def _open_start(session, start_id) -> db.ChoreStart:
    row = session.get(db.ChoreStart, start_id)
    if row is None:
        raise HTTPException(404, "no such chore start")
    if row.ended_on is not None:
        raise HTTPException(409, f"this chore isn't in progress any more ({row.end_reason})")
    return row


@router.get("/chore_starts")
def list_starts(chore: str | None = None,
                status: Literal["in_progress", "done", "stopped"] | None = None,
                limit: int = Query(50, ge=1, le=200), before: str | None = None,
                x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    S = db.ChoreStart

    def go():
        with _session() as session:
            where = []
            if chore:
                where.append(S.chore_id == _chore_id(session, chore))
            if status == "in_progress":
                where.append(db.START_OPEN)
            elif status:
                where.append(S.end_reason == status)
            if before:
                ts, sid = _parse_cursor(before)
                where.append(tuple_(S.started_on, S.id) < (ts, sid))
            found = db.chore_starts(session, *where, limit=limit + 1)
            more = len(found) > limit
            found = found[:limit]
            nxt = (_cursor(datetime.fromisoformat(found[-1]["started_on"]), found[-1]["id"])
                   if more else None)
            return {"starts": found, "next": nxt}
    return _run(go)


@router.post("/chore_starts")
def create_start(body: NewStart, tasks: BackgroundTasks, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            chore_id = _chore_id(session, body.chore)
            if session.scalar(select(db.ChoreStart.id).where(
                    db.ChoreStart.chore_id == chore_id, db.START_OPEN)) is not None:
                raise HTTPException(409, "this chore is already in progress; edit that one to "
                                         "join or take over")
            uid = db.user_id(session, body.user)
            row = db.ChoreStart(chore_id=chore_id, started_on=body.started_at or db.utcnow(),
                                reporter_id=uid, notes=body.notes, modified_by=uid)
            session.add(row)
            session.flush()
            _set_start_doers(session, row.id, body.doers or [], uid)
            session.flush()
            started = _start(session, row.id)
        tasks.add_task(chore_discord.started, started)
        return started
    return _run(go)


@router.patch("/chore_starts/{start_id}")
def edit_start(start_id: int, body: StartChanges, x_api_key: str | None = Header(None)):
    """Join, take over (change `doers`), or change when it started or the note."""
    _check_key(x_api_key)
    changes = body.model_dump(exclude_unset=True, exclude={"user"})
    if "started_at" in changes and changes["started_at"] is None:
        raise HTTPException(422, "started at can't be empty")

    def go():
        with _session() as session, session.begin():
            row = _open_start(session, start_id)
            uid = db.user_id(session, body.user)
            if "started_at" in changes:
                row.started_on = changes["started_at"]
            if "notes" in changes:
                row.notes = changes["notes"]
            if "doers" in changes:
                _set_start_doers(session, row.id, changes["doers"] or [], uid)
            row.modified_by = uid
            session.flush()
            return _start(session, start_id)
    return _run(go)


@router.post("/chore_starts/{start_id}/stop")
def stop_start(start_id: int, tasks: BackgroundTasks, user: str | None = None,
               x_api_key: str | None = Header(None)):
    _check_key(x_api_key)

    def go():
        with _session() as session, session.begin():
            row = _open_start(session, start_id)
            uid = db.user_id(session, user)
            row.ended_on, row.end_reason = db.utcnow(), "stopped"
            row.ended_by = row.modified_by = uid
            session.flush()
            stopped = _start(session, start_id)
        tasks.add_task(chore_discord.stopped, stopped)
        return stopped
    return _run(go)
