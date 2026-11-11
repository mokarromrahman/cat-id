"""Postgres models and helpers for the cat-id server (SQLAlchemy 2, sync).

Tables (every one also has created_on, modified_by, modified_on):
  app_user    people and systems that send or change data: system, pi, Ashley, Mac
  cat         Litten and Shinx (a CHECK allows only those names)
  event_type  litterbox, cough (type is the code, name the display label)
  label       Litten, Shinx, neither, both; cat_id says which cat a label means
  picture     every photo /litterbox or /identify receives, its model guess and its label;
              a crop is its own row with parent_picture_id set
  event       litterbox visits (from labeled pictures) and coughs
  vet_visit   vet visits and pickups; soft-deleted with deleted_on
View active_vet_visit is vet_visit without the soft-deleted rows.

The schema itself is created by Alembic (migrations/). The models here must match it;
`alembic check` reports any difference.

A DB failure must never break /litterbox or a Discord post: callers use safe_write(), which
logs the error and appends the row to inbox/_db_failed.jsonl for replay_db_failed.py.
"""
import fcntl
import json
import os
import threading
import time as _time
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    REAL, CheckConstraint, Date, DateTime, FetchedValue, ForeignKey, Identity, Index, Integer,
    Numeric, Text, Time, create_engine, delete, func, or_, select, text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "")
FAILED_FILE = Path(os.environ.get("DB_FAILED_FILE", "inbox/_db_failed.jsonl"))
SYSTEM_USER = "system"

CAT_NAMES = ("Litten", "Shinx")
LABEL_NAMES = ("Litten", "Shinx", "neither", "both")
PICTURE_SOURCES = ("litterbox", "identify")
PICTURE_STATUSES = ("pending", "labeled", "archived", "deleted")
VET_REASONS = ("checkup", "shots", "emergency", "food pickup", "medication pickup", "other")


def _in(column: str, values) -> str:
    """SQL for a CHECK that `column` is one of `values` (fixed strings defined above)."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Audit:
    """The three audit columns on every table. A DB trigger (see the first migration) sets
    modified_on on every insert and update, and fills modified_by with the system user when
    it's left empty, so edits made in DBeaver or psql are covered too."""
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    # FetchedValue: if the code leaves it unset, the trigger fills it and the ORM reads it back.
    modified_by: Mapped[int] = mapped_column(
        ForeignKey("app_user.id"), server_default=FetchedValue())
    modified_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue())


class AppUser(Audit, Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class Cat(Audit, Base):
    __tablename__ = "cat"
    __table_args__ = (CheckConstraint(_in("name", CAT_NAMES), name="cat_name_allowed"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    birthday: Mapped[date | None] = mapped_column(Date)
    gotcha_day: Mapped[date | None] = mapped_column(Date)


class EventType(Audit, Base):
    __tablename__ = "event_type"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    type: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)


class Label(Audit, Base):
    __tablename__ = "label"
    __table_args__ = (CheckConstraint(_in("name", LABEL_NAMES), name="label_name_allowed"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    cat_id: Mapped[int | None] = mapped_column(ForeignKey("cat.id"))


class Picture(Audit, Base):
    __tablename__ = "picture"
    __table_args__ = (
        CheckConstraint(_in("source", PICTURE_SOURCES), name="picture_source_allowed"),
        CheckConstraint(_in("status", PICTURE_STATUSES), name="picture_status_allowed"),
        # Original photo names are unique; crop names aren't (<photo>_crop1.jpg can exist in
        # both data/Litten/ and data/Shinx/).
        Index("uq_picture_original_filename", "filename", unique=True,
              postgresql_where=text("parent_picture_id IS NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    best_guess: Mapped[str | None] = mapped_column(Text)        # None on crops
    confidence: Mapped[float | None] = mapped_column(REAL)      # None on crops
    predicted_label: Mapped[str | None] = mapped_column(Text)   # includes "uncertain"
    filename: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[str] = mapped_column(Text, server_default="pending", index=True)
    final_label_id: Mapped[int | None] = mapped_column(ForeignKey("label.id"))
    labeled_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    labeled_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    model_version: Mapped[str | None] = mapped_column(Text)
    parent_picture_id: Mapped[int | None] = mapped_column(ForeignKey("picture.id"))


class Event(Audit, Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(ForeignKey("event_type.id"))
    cat_id: Mapped[int] = mapped_column(ForeignKey("cat.id", ondelete="RESTRICT"))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    picture_id: Mapped[int | None] = mapped_column(ForeignKey("picture.id"), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VetVisit(Audit, Base):
    __tablename__ = "vet_visit"
    __table_args__ = (
        CheckConstraint(
            f"cardinality(reason) > 0 AND reason <@ ARRAY[{', '.join(repr(r) for r in VET_REASONS)}]::text[]",
            name="vet_visit_reason_allowed"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cat_id: Mapped[int | None] = mapped_column(ForeignKey("cat.id"))  # None for pickups
    visit_date: Mapped[date] = mapped_column(Date, index=True)
    appointment_time: Mapped[time | None] = mapped_column(Time)    # Edmonton clock time
    doctor: Mapped[str | None] = mapped_column(Text)
    clinic: Mapped[str] = mapped_column(Text, server_default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[list[str]] = mapped_column(ARRAY(Text))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    deleted_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- connection ----------

def make_engine(url: str = DATABASE_URL):
    # Short connect timeout: a down database must not hold up /litterbox. The session time
    # zone is UTC so timestamps come back in UTC whatever the server's zone is.
    return create_engine(
        url, pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC"})


engine = make_engine() if DATABASE_URL else None
SessionLocal = sessionmaker(engine, expire_on_commit=False) if engine else None


def user_id(session: Session, name: str | None) -> int:
    """The app_user id for `name`; a missing or unknown name means the system user, so
    older clients that don't send a user keep working."""
    if name:
        found = session.scalar(select(AppUser.id).where(AppUser.name == name))
        if found is not None:
            return found
    return session.scalar(select(AppUser.id).where(AppUser.name == SYSTEM_USER))


# ---------- writes that must not fail the request ----------

# kind -> function(session, payload), registered with @writer below (picture, label, cough,
# ...). replay_db_failed.py uses the same table, so a replayed row goes through exactly the
# same code as the original request. Keep the writers in this file so the replay script
# doesn't have to import app.py.
WRITERS = {}


def writer(kind: str):
    def register(fn):
        WRITERS[kind] = fn
        return fn
    return register


def _json_default(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    raise TypeError(f"can't store {type(v).__name__} in {FAILED_FILE.name}")


def save_failed(kind: str, payload: dict, error: str):
    """Append one failed write to FAILED_FILE. flock keeps it safe while
    replay_db_failed.py is rewriting the file."""
    line = json.dumps({"kind": kind, "payload": payload, "error": error,
                       "failed_at": utcnow()}, default=_json_default)
    FAILED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_FILE, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line + "\n")


def run_writer(kind: str, payload: dict):
    """Run WRITERS[kind] in one transaction. Raises on failure."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set")
    with SessionLocal.begin() as session:
        return WRITERS[kind](session, payload)


# After a connection failure, requests skip the database until a background thread sees it
# answering again. Without this, every request would wait for the connection to fail; when
# the db container is stopped, even looking up its name can take ~20 s (seen in testing).
PROBE_EVERY = 15
_down = threading.Event()
_probe_lock = threading.Lock()


def _probe():
    from sqlalchemy import text as _text
    while _down.is_set():
        _time.sleep(PROBE_EVERY)
        try:
            with engine.connect() as conn:
                conn.execute(_text("SELECT 1"))
            _down.clear()
            print("database reachable again")
        except Exception:
            pass


def _mark_down(e):
    if isinstance(e, OperationalError) and engine is not None:
        with _probe_lock:
            if not _down.is_set():
                _down.set()
                print(f"database unreachable; skipping it until it answers (checked every {PROBE_EVERY} s)")
                threading.Thread(target=_probe, daemon=True).start()


def is_down() -> bool:
    return SessionLocal is None or _down.is_set()


def safe_write(kind: str, payload: dict, on_fail=None):
    """Run a registered writer and return what it returns. On any error, log it, keep the
    row in FAILED_FILE and return `on_fail` instead of raising. `payload` must be
    JSON-friendly (datetimes are stored as ISO text)."""
    try:
        if is_down():
            raise RuntimeError("database unavailable (retrying soon)")
        return run_writer(kind, payload)
    except Exception as e:
        _mark_down(e)
        err = f"{type(e).__name__}: {e}"
        print(f"db write '{kind}' failed, saved to {FAILED_FILE}:", err)
        try:
            save_failed(kind, payload, err)
        except Exception as e2:
            print("could not save the failed write either:", e2, payload)
        return on_fail


def safe_read(fn, default):
    """fn(session) -> value, or `default` if the database can't be reached."""
    if is_down():
        return default
    try:
        with SessionLocal() as session:
            return fn(session)
    except Exception as e:
        _mark_down(e)
        print("db read failed:", type(e).__name__, e)
        return default


def as_datetime(v) -> datetime | None:
    """Payload timestamps arrive as datetime (live request) or ISO text (replay)."""
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(v)


# ---------- reads for the label page ----------

DEFAULT_EVENT_TYPES = [{"type": "litterbox", "name": "Litterbox"}, {"type": "cough", "name": "Cough"}]
NO_EVENT = "none"  # event_type value meaning "label only, no event"


def event_types() -> list[dict]:
    """[{type, name}] for the label page's event picker (the seeded list if the DB is down)."""
    return safe_read(
        lambda s: [{"type": t, "name": n} for t, n in
                   s.execute(select(EventType.type, EventType.name).order_by(EventType.id))],
        DEFAULT_EVENT_TYPES)


def picture_sources(names: list[str]) -> dict:
    """{filename: source} for original photos; names with no row are left out."""
    if not names:
        return {}
    return safe_read(
        lambda s: dict(s.execute(select(Picture.filename, Picture.source).where(
            Picture.filename.in_(names), Picture.parent_picture_id.is_(None))).tuples().all()),
        {})


# ---------- writers (see WRITERS above) ----------
# Each returns a short message for the label page's History panel, or None.

def _original(session, filename):
    return session.scalar(select(Picture).where(
        Picture.filename == filename, Picture.parent_picture_id.is_(None)))


def _no_row(name):
    return f"No database row for {name} (it arrived before the database or during an outage), so no event"


def default_event_type(source: str) -> str:
    """Event type used when the label page doesn't say: litterbox photos are litterbox
    visits, anything else is label-only."""
    return "litterbox" if source == "litterbox" else NO_EVENT


def _maybe_event(session, pic: Picture, original: Picture, label: Label | None,
                 event_type: str | None, uid: int):
    """Create the event a label asks for, if any. Rules: the label must be a cat (Litten or
    Shinx); event_type None means the default for the photo's source; "none" means no event;
    never two events for the same original photo, cat and event type."""
    if label is None or label.cat_id is None:
        return None
    code = event_type if event_type is not None else default_event_type(original.source)
    if code == NO_EVENT or not code:
        return None
    et = session.scalar(select(EventType).where(EventType.type == code))
    if et is None:
        return f"Unknown event type '{code}', no event"
    dup = session.scalar(
        select(Event.id).join(Picture, Event.picture_id == Picture.id).where(
            or_(Picture.id == original.id, Picture.parent_picture_id == original.id),
            Event.cat_id == label.cat_id, Event.event_type_id == et.id))
    if dup is not None:
        return f"{et.name} for {label.name} already recorded for this photo, no new event"
    session.add(Event(event_type_id=et.id, cat_id=label.cat_id, reporter_id=pic.reporter_id,
                      picture_id=pic.id, event_timestamp=pic.event_timestamp, modified_by=uid))
    return f"{et.name} event recorded for {label.name}"


@writer("picture")
def add_picture(session, p):
    """A photo /litterbox or /identify just saved to inbox/."""
    if _original(session, p["filename"]) is not None:
        return None  # already recorded (a replayed line, or two photos in the same second)
    uid = user_id(session, p.get("user"))
    session.add(Picture(
        event_timestamp=as_datetime(p["event_timestamp"]), best_guess=p["best_guess"],
        confidence=p["confidence"], predicted_label=p["predicted_label"],
        filename=p["filename"], file_path=p["file_path"], source=p["source"],
        reporter_id=uid, model_version=p.get("model_version"), modified_by=uid))
    return None


@writer("label")
def label_picture(session, p):
    """The whole photo was labeled on /label and moved to p["file_path"]."""
    pic = _original(session, p["name"])
    if pic is None:
        return _no_row(p["name"])
    uid = user_id(session, p.get("user"))
    label = session.scalar(select(Label).where(Label.name == p["label"]))
    pic.status, pic.file_path = "labeled", p["file_path"]
    pic.final_label_id = label.id if label else None
    pic.labeled_on, pic.labeled_by, pic.modified_by = utcnow(), uid, uid
    session.flush()
    return _maybe_event(session, pic, pic, label, p.get("event_type"), uid)


@writer("crop")
def crop_picture(session, p):
    """A crop of p["name"] was saved as its own labeled photo."""
    orig = _original(session, p["name"])
    if orig is None:
        return _no_row(p["name"])
    uid = user_id(session, p.get("user"))
    label = session.scalar(select(Label).where(Label.name == p["label"]))
    crop = Picture(
        event_timestamp=orig.event_timestamp, filename=p["crop_name"],
        file_path=p["crop_path"], source=orig.source, reporter_id=orig.reporter_id,
        status="labeled", final_label_id=label.id if label else None,
        labeled_on=utcnow(), labeled_by=uid, parent_picture_id=orig.id,
        model_version=orig.model_version, modified_by=uid)
    session.add(crop)
    if p.get("archived_path"):  # "keep original" was off: the original went to _archived
        orig.status, orig.file_path, orig.modified_by = "archived", p["archived_path"], uid
    session.flush()
    return _maybe_event(session, crop, orig, label, p.get("event_type"), uid)


@writer("archive")
def archive_picture(session, p):
    pic = _original(session, p["name"])
    if pic is None:
        return None
    uid = user_id(session, p.get("user"))
    pic.status, pic.file_path, pic.modified_by = "archived", p["file_path"], uid
    return None


@writer("delete")
def delete_picture(session, p):
    """The file was deleted; the row stays, marked deleted."""
    pic = _original(session, p["name"])
    if pic is None:
        return None
    pic.status, pic.modified_by = "deleted", user_id(session, p.get("user"))
    return None


@writer("undo")
def undo_picture(session, p):
    """Undo on /label put the photo back in inbox/. Remove the event the undone action
    created (the one hard delete of events) and make the photo pending again."""
    orig = _original(session, p["name"])
    uid = user_id(session, p.get("user"))
    removed = 0
    if p["kind"] == "crop":
        crop = None
        if orig is not None:
            crop = session.scalar(select(Picture).where(
                Picture.parent_picture_id == orig.id, Picture.file_path == p["crop_path"])
                .order_by(Picture.id.desc()))
        if crop is not None:
            removed = session.execute(delete(Event).where(Event.picture_id == crop.id)).rowcount
            session.delete(crop)
    elif orig is not None:
        removed = session.execute(delete(Event).where(Event.picture_id == orig.id)).rowcount
        orig.final_label_id = orig.labeled_on = orig.labeled_by = None
    if orig is not None:
        orig.status, orig.file_path, orig.modified_by = "pending", p["orig_path"], uid
    return "Event removed" if removed else None


@writer("cough")
def add_cough(session, p):
    cat_id = session.scalar(select(Cat.id).where(Cat.name == p["cat"]))
    if cat_id is None:
        print(f"cough for unknown cat {p['cat']!r}: no event recorded")
        return None
    uid = user_id(session, p.get("user"))
    et = session.scalar(select(EventType.id).where(EventType.type == "cough"))
    session.add(Event(event_type_id=et, cat_id=cat_id, reporter_id=uid, notes=p.get("notes"),
                      event_timestamp=as_datetime(p["event_timestamp"]), modified_by=uid))
    return None
