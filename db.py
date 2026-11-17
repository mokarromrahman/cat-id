"""Postgres models and helpers for the cat-id server (SQLAlchemy 2, sync).

Tables (every one also has created_on, modified_by, modified_on):
  app_user    people and systems that send or change data: system, pi, Ashley, Mac
  cat         Litten and Shinx (a CHECK allows only those names)
  event_type  litterbox, cough (type is the code, name the display label)
  label       Litten, Shinx, neither, both; cat_id says which cat a label means
  picture     every photo /litterbox, /identify or /cough receives, its model guess and its label;
              a crop is its own row with parent_picture_id set
  event       litterbox visits (from labeled pictures) and coughs; a visit can have a location
  vet_visit   vet visits and pickups; soft-deleted with deleted_on
  location    where a litterbox is: basement, master_bathroom (name is the code, label_name
              the display label)
  litterbox_clean_event  a litterbox was cleaned (POST /litterbox_clean), and whether the
              bag was changed; not tied to a cat
  chore       household chores (name is the code, label_name the display label) and how many
              days may pass before one counts as overdue (warning_threshold_days; null = never)
  chore_event a chore was done (chores_api.py); soft-deleted with deleted_on
  chore_event_doer  who did it: one row per person per chore_event (none = not recorded)
  chore_start a chore is being done right now (Start), by whom (chore_start_doer); ended by
              its Done or by Stop; at most one in progress per chore
  chore_request  a chore was marked as needing to be done (note, quantity + unit, needed-by
              date); closed by the next Done or cancelled; at most one open per chore
  deleted_row a copy of every row hard-deleted from any other table (a trigger fills it), for
              the Databricks export
  export_state how far export_databricks.py has sent each table
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
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import (
    REAL, Boolean, CheckConstraint, Date, DateTime, FetchedValue, ForeignKey, Identity, Index, Integer,
    Numeric, Text, Time, UniqueConstraint, create_engine, delete, func, or_, select, text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, aliased, mapped_column, sessionmaker

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
    # A person (Ashley, Mac, a cleaner ...), not a system or device (system, pi). Only people
    # can be picked as who did a chore.
    human: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


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
    # Which litterbox the photo is of (/litterbox photos); None for /identify and cough photos.
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))


class Event(Audit, Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(ForeignKey("event_type.id"))
    cat_id: Mapped[int] = mapped_column(ForeignKey("cat.id", ondelete="RESTRICT"))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    picture_id: Mapped[int | None] = mapped_column(ForeignKey("picture.id"), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Which litterbox a visit was in (copied from its photo, or picked in the app); None for
    # coughs and for visits where it isn't known.
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"))


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


class Location(Audit, Base):
    __tablename__ = "location"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)    # code: basement, master_bathroom
    label_name: Mapped[str] = mapped_column(Text)            # display: Basement, Master Bathroom


class LitterboxCleanEvent(Audit, Base):
    __tablename__ = "litterbox_clean_event"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id", ondelete="RESTRICT"))
    # When it was cleaned (picked in the app; default when it was sent) ...
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # ... and when the request reached the server (created_on differs only for a replayed row).
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    bag_changed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)


class Chore(Audit, Base):
    __tablename__ = "chore"
    __table_args__ = (
        CheckConstraint("name ~ '^[a-z0-9_]+$'", name="chore_name_code"),
        CheckConstraint("warning_threshold_days > 0", name="chore_warning_threshold_positive"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)    # code: vacuum, cat_food_pickup
    label_name: Mapped[str] = mapped_column(Text)            # display: Vacuum, Cat Food Pickup
    # Overdue when more than this many days (x 24 h) have passed since it was last done, or
    # it was never done. None: no reminder.
    warning_threshold_days: Mapped[int | None] = mapped_column(Integer)
    # False hides the chore (a chore with events can't be deleted).
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ChoreEvent(Audit, Base):
    __tablename__ = "chore_event"
    __table_args__ = (
        Index("ix_chore_event_chore_id_event_timestamp", "chore_id", "event_timestamp"),
        CheckConstraint("started_on <= event_timestamp", name="chore_event_started_before_done"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chore_id: Mapped[int] = mapped_column(ForeignKey("chore.id", ondelete="RESTRICT"))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # When it was started (its chore_start, or typed in); None = not known. The time it took
    # is event_timestamp - started_on.
    started_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChoreEventDoer(Audit, Base):
    """Who did a chore: one row per person (app_user with human = true) per chore_event."""
    __tablename__ = "chore_event_doer"
    __table_args__ = (UniqueConstraint("chore_event_id", "app_user_id", name="uq_chore_event_doer"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chore_event_id: Mapped[int] = mapped_column(ForeignKey("chore_event.id", ondelete="CASCADE"))
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))


class ChoreStart(Audit, Base):
    """Someone is doing a chore right now (chores_api.py). In progress until the chore's next
    Done (end_reason done, chore_event_id) or Stop (end_reason stopped); at most one in
    progress per chore (partial unique index). Who: chore_start_doer."""
    __tablename__ = "chore_start"
    __table_args__ = (
        CheckConstraint("end_reason IN ('done', 'stopped')", name="chore_start_end_reason"),
        CheckConstraint("(ended_on IS NULL) = (end_reason IS NULL)", name="chore_start_ended"),
        Index("ix_chore_start_chore_id_started_on", "chore_id", "started_on"),
        Index("uq_chore_start_open", "chore_id", unique=True,
              postgresql_where=text("ended_on IS NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chore_id: Mapped[int] = mapped_column(ForeignKey("chore.id", ondelete="RESTRICT"))
    started_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    ended_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)    # done / stopped
    # The Done that ended it. Deleting that Done puts it back in progress.
    chore_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("chore_event.id", ondelete="SET NULL"))
    ended_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    discord_message_id: Mapped[str | None] = mapped_column(Text)


class ChoreStartDoer(Audit, Base):
    """Who is doing a started chore: one row per person (app_user.human) per chore_start."""
    __tablename__ = "chore_start_doer"
    __table_args__ = (UniqueConstraint("chore_start_id", "app_user_id", name="uq_chore_start_doer"),)
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chore_start_id: Mapped[int] = mapped_column(ForeignKey("chore_start.id", ondelete="CASCADE"))
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))


class ChoreRequest(Audit, Base):
    """Someone marked a chore as needing to be done (chores_api.py). Open until a Done is
    recorded for that chore (done_on, chore_event_id) or it's cancelled (cancelled_on); at
    most one open request per chore (partial unique index)."""
    __tablename__ = "chore_request"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="chore_request_quantity_positive"),
        CheckConstraint("done_on IS NULL OR cancelled_on IS NULL",
                        name="chore_request_done_or_cancelled"),
        Index("ix_chore_request_chore_id_requested_on", "chore_id", "requested_on"),
        Index("uq_chore_request_open", "chore_id", unique=True,
              postgresql_where=text("done_on IS NULL AND cancelled_on IS NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    chore_id: Mapped[int] = mapped_column(ForeignKey("chore.id", ondelete="RESTRICT"))
    requested_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reporter_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # free number ...
    unit: Mapped[str | None] = mapped_column(Text)                    # ... plus a free unit
    # An Edmonton day; past the end of it the chore counts as overdue.
    needed_by: Mapped[date | None] = mapped_column(Date)
    done_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The Done that closed it. Deleting that Done reopens the request.
    chore_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("chore_event.id", ondelete="SET NULL"))
    cancelled_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who did it (the Done's reporter) or cancelled it.
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    # The webhook message announcing it, so it can be edited when it's done or cancelled.
    discord_message_id: Mapped[str | None] = mapped_column(Text)


class DeletedRow(Audit, Base):
    """A copy of every row hard-deleted from any other table (trigger record_deleted_row,
    migration 0006), so export_databricks.py can tell Databricks about deletes. Today these are
    undo's events and crop pictures, chore doers removed from a start, and cascaded doers.
    modified_by is always the system user (a trigger can't know who deleted it)."""
    __tablename__ = "deleted_row"
    __table_args__ = (
        Index("ix_deleted_row_table_name_modified_on", "table_name", "modified_on"),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    table_name: Mapped[str] = mapped_column(Text)
    row_id: Mapped[int] = mapped_column(Integer)       # the deleted row's id
    row_data: Mapped[dict] = mapped_column(JSONB)       # the whole row, to_jsonb(OLD)
    deleted_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExportState(Audit, Base):
    """How far export_databricks.py has sent each table: rows with modified_on after
    exported_through are sent next time. Delete a table's row to send it all again."""
    __tablename__ = "export_state"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    table_name: Mapped[str] = mapped_column(Text, unique=True)
    exported_through: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_file: Mapped[str | None] = mapped_column(Text)   # None when nothing changed
    last_row_count: Mapped[int] = mapped_column(Integer)


# Tables export_databricks.py never sends as their own folder: deleted_row goes out inside
# each table's files (as rows flagged _deleted), export_state is the exporter's bookkeeping.
NOT_EXPORTED = ("deleted_row", "export_state")


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


DEFAULT_LOCATIONS = [{"name": "basement", "label_name": "Basement"},
                     {"name": "master_bathroom", "label_name": "Master Bathroom"}]


def locations() -> list[dict]:
    """[{name, label_name}] in id order (the seeded list if the DB is down)."""
    return safe_read(
        lambda s: [{"name": n, "label_name": l} for n, l in
                   s.execute(select(Location.name, Location.label_name).order_by(Location.id))],
        DEFAULT_LOCATIONS)


def litterbox_status():
    """For GET /health: per location, when it was last cleaned and when its bag was last
    changed (UTC ISO text, or None if never). None if the database can't be reached."""
    def read(s):
        last = (select(LitterboxCleanEvent.location_id,
                       func.max(LitterboxCleanEvent.event_timestamp).label("cleaned"),
                       func.max(LitterboxCleanEvent.event_timestamp)
                       .filter(LitterboxCleanEvent.bag_changed).label("bag"))
                .group_by(LitterboxCleanEvent.location_id).subquery())
        rows = s.execute(
            select(Location.name, Location.label_name, last.c.cleaned, last.c.bag)
            .outerjoin(last, last.c.location_id == Location.id).order_by(Location.id))
        return [{"location": n, "name": l, "last_cleaned": _iso(c), "bag_last_changed": _iso(b)}
                for n, l, c, b in rows]
    return safe_read(read, None)


def _iso(t):
    return t.astimezone(timezone.utc).isoformat() if t else None


def chore_rows(session, include_inactive: bool = False, now: datetime | None = None) -> list[dict]:
    """Each chore (id order) with when it was last done and by whom (soft-deleted events
    don't count), when it's due, its open request (or None) and whether it's overdue (more
    than warning_threshold_days x 24 h since it was last done, or never done; never overdue
    on that count without a threshold; also overdue once the open request's needed_by day
    is over)."""
    now = now or utcnow()
    live = ChoreEvent.deleted_on.is_(None)
    # The newest live event per chore (DISTINCT ON keeps the first row of each chore).
    latest = (select(ChoreEvent.chore_id, ChoreEvent.id, ChoreEvent.event_timestamp)
              .where(live).distinct(ChoreEvent.chore_id)
              .order_by(ChoreEvent.chore_id, ChoreEvent.event_timestamp.desc(),
                        ChoreEvent.id.desc()).subquery())
    q = (select(Chore, latest.c.id, latest.c.event_timestamp)
         .outerjoin(latest, latest.c.chore_id == Chore.id).order_by(Chore.id))
    if not include_inactive:
        q = q.where(Chore.active)
    rows = session.execute(q).all()
    doers = chore_doers(session, [eid for _, eid, _ in rows if eid is not None])
    requests = {r["chore_id"]: r for r in chore_requests(session, REQUEST_OPEN, now=now)}
    starts = {r["chore_id"]: r for r in chore_starts(session, START_OPEN)}
    out = []
    for c, eid, last in rows:
        days = c.warning_threshold_days
        due = last + timedelta(days=days) if days and last else None
        request = requests.get(c.id)
        out.append({
            "id": c.id, "name": c.name, "label_name": c.label_name,
            "warning_threshold_days": days, "active": c.active,
            "last_done": _iso(last), "last_done_by": doers.get(eid, []),
            "due_at": _iso(due),
            "overdue": (bool(days) and (last is None or now > due))
                       or bool(request and request["overdue"]),
            "request": request,
            "in_progress": starts.get(c.id),
        })
    return out


EDMONTON = ZoneInfo("America/Edmonton")
REQUEST_OPEN = ChoreRequest.done_on.is_(None) & ChoreRequest.cancelled_on.is_(None)
START_OPEN = ChoreStart.ended_on.is_(None)


def start_doers(session, start_ids) -> dict:
    """{chore_start id: [person names, alphabetical]}."""
    if not start_ids:
        return {}
    found = {}
    for sid, name in session.execute(
            select(ChoreStartDoer.chore_start_id, AppUser.name)
            .join(AppUser, AppUser.id == ChoreStartDoer.app_user_id)
            .where(ChoreStartDoer.chore_start_id.in_(start_ids)).order_by(AppUser.name)):
        found.setdefault(sid, []).append(name)
    return found


def chore_starts(session, *where, limit: int | None = None) -> list[dict]:
    """Start dicts (see chores_api.py) for the chore_start rows matching `where`, newest
    first."""
    reporter, ender = aliased(AppUser), aliased(AppUser)
    q = (select(ChoreStart, Chore.name, Chore.label_name, reporter.name, ender.name)
         .join(Chore, Chore.id == ChoreStart.chore_id)
         .join(reporter, reporter.id == ChoreStart.reporter_id)
         .outerjoin(ender, ender.id == ChoreStart.ended_by)
         .where(*where)
         .order_by(ChoreStart.started_on.desc(), ChoreStart.id.desc()))
    if limit is not None:
        q = q.limit(limit)
    rows = session.execute(q).all()
    doers = start_doers(session, [r.id for r, *_ in rows])
    return [{
        "id": r.id, "chore_id": r.chore_id, "chore": name, "chore_label": label,
        "started_on": _iso(r.started_on), "doers": doers.get(r.id, []), "reporter": rep,
        "notes": r.notes, "status": r.end_reason or "in_progress", "ended_on": _iso(r.ended_on),
        "ended_by": ended, "chore_event_id": r.chore_event_id,
    } for r, name, label, rep, ended in rows]


def needed_by_passed(needed_by: date | None, now: datetime) -> bool:
    """True once the Edmonton day `needed_by` is over."""
    if needed_by is None:
        return False
    nxt = needed_by + timedelta(days=1)
    return now >= datetime(nxt.year, nxt.month, nxt.day, tzinfo=EDMONTON)


def chore_requests(session, *where, limit: int | None = None, now: datetime | None = None) -> list[dict]:
    """Request dicts (see chores_api.py) for the chore_request rows matching `where`, newest
    first."""
    now = now or utcnow()
    reporter, closer = aliased(AppUser), aliased(AppUser)
    q = (select(ChoreRequest, Chore.name, Chore.label_name, reporter.name, closer.name)
         .join(Chore, Chore.id == ChoreRequest.chore_id)
         .join(reporter, reporter.id == ChoreRequest.reporter_id)
         .outerjoin(closer, closer.id == ChoreRequest.closed_by)
         .where(*where)
         .order_by(ChoreRequest.requested_on.desc(), ChoreRequest.id.desc()))
    if limit is not None:
        q = q.limit(limit)
    rows = session.execute(q).all()
    doers = chore_doers(session, [r.chore_event_id for r, *_ in rows if r.chore_event_id])
    out = []
    for r, name, label, rep, closed in rows:
        status = "done" if r.done_on else "cancelled" if r.cancelled_on else "open"
        out.append({
            "id": r.id, "chore_id": r.chore_id, "chore": name, "chore_label": label,
            "requested_on": _iso(r.requested_on), "requested_by": rep,
            "notes": r.notes, "quantity": float(r.quantity) if r.quantity is not None else None,
            "unit": r.unit, "needed_by": r.needed_by.isoformat() if r.needed_by else None,
            "status": status, "done_on": _iso(r.done_on), "chore_event_id": r.chore_event_id,
            "done_by": doers.get(r.chore_event_id, []) if status == "done" else [],
            "cancelled_on": _iso(r.cancelled_on),
            "closed_by": closed,
            "overdue": status == "open" and needed_by_passed(r.needed_by, now),
        })
    return out


def chore_doers(session, event_ids) -> dict:
    """{chore_event id: [person names, alphabetical]}."""
    if not event_ids:
        return {}
    found = {}
    for eid, name in session.execute(
            select(ChoreEventDoer.chore_event_id, AppUser.name)
            .join(AppUser, AppUser.id == ChoreEventDoer.app_user_id)
            .where(ChoreEventDoer.chore_event_id.in_(event_ids)).order_by(AppUser.name)):
        found.setdefault(eid, []).append(name)
    return found


def chore_status():
    """For GET /health: the active chores (see chore_rows). None if the database can't be
    reached."""
    return safe_read(chore_rows, None)


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
    # event.picture_id is unique: a photo sent with a cough report already has its event.
    linked = session.scalar(select(EventType.name).join(Event).where(Event.picture_id == pic.id))
    if linked is not None:
        return f"This photo already has a {linked} event, no new event"
    dup = session.scalar(
        select(Event.id).join(Picture, Event.picture_id == Picture.id).where(
            or_(Picture.id == original.id, Picture.parent_picture_id == original.id),
            Event.cat_id == label.cat_id, Event.event_type_id == et.id))
    if dup is not None:
        return f"{et.name} for {label.name} already recorded for this photo, no new event"
    # A litterbox visit happened where the photo was taken; other types have no location.
    session.add(Event(event_type_id=et.id, cat_id=label.cat_id, reporter_id=pic.reporter_id,
                      picture_id=pic.id, event_timestamp=pic.event_timestamp,
                      location_id=original.location_id if code == "litterbox" else None,
                      modified_by=uid))
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
        reporter_id=uid, model_version=p.get("model_version"),
        location_id=_location_id(session, p.get("location")), modified_by=uid))
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
    # now() is the transaction start, the same as the created_on of an event made below;
    # undo uses that to tell it apart from an event that was already there (a cough's).
    pic.labeled_on, pic.labeled_by, pic.modified_by = func.now(), uid, uid
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
        model_version=orig.model_version, location_id=orig.location_id, modified_by=uid)
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
        # Only an event the label made (created in the labeling transaction). A cough sent
        # with this photo is older and stays; archive and delete never make one.
        if orig.labeled_on is not None:
            removed = session.execute(delete(Event).where(
                Event.picture_id == orig.id, Event.created_on >= orig.labeled_on)).rowcount
        orig.final_label_id = orig.labeled_on = orig.labeled_by = None
    if orig is not None:
        orig.status, orig.file_path, orig.modified_by = "pending", p["orig_path"], uid
    return "Event removed" if removed else None


def _location_id(session, name: str | None) -> int | None:
    """location.id for a location name; None for no name or an unknown one."""
    if not name:
        return None
    return session.scalar(select(Location.id).where(Location.name == name))


def _add_reported_event(session, p, type_code: str):
    """An event someone reported from the app (cat picked by hand), with an optional note,
    photo and location. No event for an unknown cat name."""
    cat_id = session.scalar(select(Cat.id).where(Cat.name == p["cat"]))
    if cat_id is None:
        print(f"{type_code} for unknown cat {p['cat']!r}: no event recorded")
        return None
    uid = user_id(session, p.get("user"))
    et = session.scalar(select(EventType.id).where(EventType.type == type_code))
    # A photo sent with the report: its picture row is written just before this (same
    # request, and in the same order in the failed file), so look it up by name.
    pic = _original(session, p["photo"]) if p.get("photo") else None
    if pic is not None and session.scalar(select(Event.id).where(Event.picture_id == pic.id)):
        pic = None  # name clash with another photo from the same second that has an event
    if p.get("photo") and pic is None:
        print(f"{type_code} photo {p['photo']!r} has no free picture row: event recorded without it")
    session.add(Event(event_type_id=et, cat_id=cat_id, reporter_id=uid, notes=p.get("notes"),
                      picture_id=pic.id if pic else None,
                      location_id=_location_id(session, p.get("location")),
                      event_timestamp=as_datetime(p["event_timestamp"]), modified_by=uid))
    return None


@writer("cough")
def add_cough(session, p):
    """POST /cough."""
    return _add_reported_event(session, p, "cough")


@writer("litterbox_report")
def add_litterbox_report(session, p):
    """POST /litterbox with a `cat` (the app's Add litterbox sheet). The Pi's photos get
    their events from labeling instead."""
    return _add_reported_event(session, p, "litterbox")


@writer("litterbox_clean")
def add_litterbox_clean(session, p):
    """POST /litterbox_clean (the app's Add event > Clean Litterbox). No row for an unknown
    location name (the endpoint checks it first, so only a replay of a since-removed
    location gets here)."""
    loc = _location_id(session, p["location"])
    if loc is None:
        print(f"litterbox clean for unknown location {p['location']!r}: nothing recorded")
        return None
    uid = user_id(session, p.get("user"))
    session.add(LitterboxCleanEvent(
        location_id=loc, event_timestamp=as_datetime(p["event_timestamp"]),
        server_timestamp=as_datetime(p["server_timestamp"]), reporter_id=uid,
        bag_changed=bool(p["bag_changed"]), notes=p.get("notes"), modified_by=uid))
    return None
