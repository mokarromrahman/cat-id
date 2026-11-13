"""Event endpoints for the app's Events tab (view only). Included by app.py.

All of them check API_KEY in the X-API-Key header and need the database (503 if it's down).

GET /event_types              [{type, name}] in table order: the Event filter and chart pages
GET /events                   events, newest first, plus totals and chart data. Query:
      cat=Litten|Shinx        (left out = both cats)
      type=<event_type code>  (left out = all types)
      from=YYYY-MM-DD, to=YYYY-MM-DD   days in Edmonton time, both included
                              (left out = the last 7 days ending today)
      limit=1..200            (default 50)
      before=<next>           the `next` value of the previous page (Load more)
    -> {"events": [event, ...], "next": "<cursor>" | null,
        "range": {"from", "to", "days", "time_zone"},
        "totals": {"all": n, "by_cat": {cat: n}, "by_type": {type: {cat: n}}},
        "chart": {"kind": "bar" | "line", "bucket": "hour" | "day" | "week",
                  "buckets": ["<bucket start, Edmonton time>", ...],
                  "series": {type: {cat: [count per bucket]}}}}
    totals and chart cover the whole filtered range (not just this page) and are only sent
    on the first page (no `before`). Chart: a single day is counted per hour, up to 31 days
    per day as bars, longer per day as lines, and past 183 days per week (7-day buckets
    starting at `from`). Every type and cat in the filter gets a series, zeros included.
    An event: {"id", "type", "type_name", "cat", "event_timestamp" (UTC), "reporter", "notes",
               "picture": null | {"id", "source", "status", "best_guess", "confidence",
                                  "labeled_by", "has_image"}}
GET /picture/{id}/image       the photo file, wherever it is now (inbox/ or data/<cat>/);
                              404 if the photo was deleted or the file is gone
"""
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, tuple_
from sqlalchemy.orm import aliased

import db

API_KEY = os.environ.get("API_KEY", "")
TZ = ZoneInfo("America/Edmonton")
PHOTO_ROOTS = [Path("data").resolve(), Path("inbox").resolve()]
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_DAYS = 3 * 366
router = APIRouter()


def _check_key(key: str | None):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")


def _session():
    if db.is_down():
        raise HTTPException(503, "database unavailable")
    return db.SessionLocal()


def _db_error(e):
    db._mark_down(e)
    return HTTPException(503, f"database unavailable ({type(e).__name__})")


def local_midnight(d: date) -> datetime:
    """The UTC instant when day `d` starts in Edmonton (handles daylight saving)."""
    return datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc)


def _cursor(ts: datetime, event_id: int) -> str:
    return f"{(ts - EPOCH) // timedelta(microseconds=1)}_{event_id}"


def _parse_cursor(s: str):
    try:
        micros, event_id = s.split("_")
        return EPOCH + timedelta(microseconds=int(micros)), int(event_id)
    except ValueError:
        raise HTTPException(422, "bad 'before' value; use the 'next' from the previous page")


def chart_layout(frm: date, to: date):
    """(kind, bucket, bucket starts as UTC datetimes, labels) for the range."""
    days = (to - frm).days + 1
    start, end = local_midnight(frm), local_midnight(to + timedelta(days=1))
    if days == 1:
        # Step through UTC so a 23- or 25-hour daylight-saving day gets the right hours.
        starts, t = [], start
        while t < end:
            starts.append(t)
            t += timedelta(hours=1)
        labels = [s.astimezone(TZ).isoformat(timespec="minutes") for s in starts]
        return "bar", "hour", starts, labels
    if days <= 183:
        dates = [frm + timedelta(days=i) for i in range(days)]
        return ("bar" if days <= 31 else "line"), "day", [local_midnight(d) for d in dates], \
            [d.isoformat() for d in dates]
    dates = [frm + timedelta(days=i) for i in range(0, days, 7)]
    return "line", "week", [local_midnight(d) for d in dates], [d.isoformat() for d in dates]


def bucket_index(ts: datetime, starts: list[datetime]) -> int:
    """Index of the bucket `ts` falls in (starts are sorted bucket start times)."""
    lo, hi = 0, len(starts) - 1
    while lo < hi:  # last start <= ts
        mid = (lo + hi + 1) // 2
        if starts[mid] <= ts:
            lo = mid
        else:
            hi = mid - 1
    return lo


@router.get("/event_types")
def event_types(x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    try:
        with _session() as session:
            rows = session.execute(
                select(db.EventType.type, db.EventType.name).order_by(db.EventType.id))
            return [{"type": t, "name": n} for t, n in rows]
    except HTTPException:
        raise
    except db.OperationalError as e:
        raise _db_error(e)


@router.get("/events")
def list_events(
    cat: Literal["Litten", "Shinx"] | None = None,
    type: str | None = None,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = None,
    x_api_key: str | None = Header(None),
):
    _check_key(x_api_key)
    today = datetime.now(TZ).date()
    to = to or today
    frm = frm or (to - timedelta(days=6))
    if frm > to:
        raise HTTPException(422, "'from' must be on or before 'to'")
    if (to - frm).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"the range can be at most {MAX_DAYS} days")
    start, end = local_midnight(frm), local_midnight(to + timedelta(days=1))
    cursor = _parse_cursor(before) if before else None

    try:
        with _session() as session:
            types = list(session.execute(
                select(db.EventType.id, db.EventType.type).order_by(db.EventType.id)))
            if type is not None and type not in {t for _, t in types}:
                raise HTTPException(422, f"unknown event type '{type}'")
            cats = [cat] if cat else list(session.scalars(select(db.Cat.name).order_by(db.Cat.id)))

            where = [db.Event.event_timestamp >= start, db.Event.event_timestamp < end]
            if cat:
                where.append(db.Cat.name == cat)
            if type:
                where.append(db.EventType.type == type)

            reporter, labeler = aliased(db.AppUser), aliased(db.AppUser)
            q = (select(db.Event, db.EventType.type, db.EventType.name, db.Cat.name,
                        reporter.name, db.Picture, labeler.name)
                 .join(db.EventType, db.EventType.id == db.Event.event_type_id)
                 .join(db.Cat, db.Cat.id == db.Event.cat_id)
                 .join(reporter, reporter.id == db.Event.reporter_id)
                 .outerjoin(db.Picture, db.Picture.id == db.Event.picture_id)
                 .outerjoin(labeler, labeler.id == db.Picture.labeled_by)
                 .where(*where))
            if cursor:
                q = q.where(tuple_(db.Event.event_timestamp, db.Event.id) < tuple_(*cursor))
            q = q.order_by(db.Event.event_timestamp.desc(), db.Event.id.desc()).limit(limit + 1)
            rows = session.execute(q).all()

            events = []
            for ev, tcode, tname, cname, rep, pic, lab in rows[:limit]:
                events.append({
                    "id": ev.id, "type": tcode, "type_name": tname, "cat": cname,
                    "event_timestamp": ev.event_timestamp.astimezone(timezone.utc).isoformat(),
                    "reporter": rep, "notes": ev.notes,
                    "picture": None if pic is None else {
                        "id": pic.id, "source": pic.source, "status": pic.status,
                        "best_guess": pic.best_guess,
                        "confidence": round(pic.confidence, 3) if pic.confidence is not None else None,
                        "labeled_by": lab, "has_image": pic.status != "deleted",
                    },
                })
            last = rows[limit - 1][0] if len(rows) > limit else None
            body = {
                "events": events,
                "next": _cursor(last.event_timestamp, last.id) if last else None,
                "range": {"from": frm.isoformat(), "to": to.isoformat(),
                          "days": (to - frm).days + 1, "time_zone": "America/Edmonton"},
            }
            if cursor is None:
                body.update(_totals_and_chart(session, where, frm, to, cats,
                                              [t for _, t in types if type in (None, t)]))
            return body
    except HTTPException:
        raise
    except db.OperationalError as e:
        raise _db_error(e)


def _totals_and_chart(session, where, frm, to, cats, type_codes):
    kind, bucket, starts, labels = chart_layout(frm, to)
    series = {t: {c: [0] * len(starts) for c in cats} for t in type_codes}
    by_cat = {c: 0 for c in cats}
    by_type = {t: {c: 0 for c in cats} for t in type_codes}
    rows = session.execute(
        select(db.Event.event_timestamp, db.Cat.name, db.EventType.type)
        .join(db.EventType, db.EventType.id == db.Event.event_type_id)
        .join(db.Cat, db.Cat.id == db.Event.cat_id)
        .where(*where))
    total = 0
    for ts, cname, tcode in rows:
        if tcode not in series or cname not in by_cat:
            continue
        total += 1
        by_cat[cname] += 1
        by_type[tcode][cname] += 1
        series[tcode][cname][bucket_index(ts.astimezone(timezone.utc), starts)] += 1
    return {
        "totals": {"all": total, "by_cat": by_cat, "by_type": by_type},
        "chart": {"kind": kind, "bucket": bucket, "buckets": labels, "series": series},
    }


@router.get("/picture/{picture_id}/image")
def picture_image(picture_id: int, x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    try:
        with _session() as session:
            pic = session.get(db.Picture, picture_id)
    except HTTPException:
        raise
    except db.OperationalError as e:
        raise _db_error(e)
    if pic is None or pic.status == "deleted":
        raise HTTPException(404, "no such photo")
    path = Path(pic.file_path).resolve()
    # Only ever serve files from the photo folders, whatever file_path says.
    if not any(path.is_relative_to(root) for root in PHOTO_ROOTS) or not path.is_file():
        raise HTTPException(404, "photo file not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=600"})
