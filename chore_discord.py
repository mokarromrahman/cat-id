"""Discord posts for chores, to CHORES_DISCORD_WEBHOOK_URL (nothing is sent if it isn't set).

Called from chores_api.py as background tasks (after the response), so Discord being slow or
down never holds up or fails a request; a failed post is only logged.

- A chore marked as needed: one message, whose id is kept on the chore_request row.
- Done (any chore, with or without a request): a new "done" message. If it closed a
  request, the request's message is also edited to show it's done (✅, struck through, who
  and when) and the new message links to it. Edits don't notify anyone; the new message does.
- Cancelled: the same, with ❌.
- The Done that closed a request deleted: the request's message goes back to "needed" and a
  new message says so; restoring the Done edits it back to done.
- Request edited (note, quantity, needed-by): the request's message is edited.
- Started: "▶️ <chore> started by ...", its message id kept on the chore_start row. Its Done
  edits it to ✅ (with the time it took) and the new "done" message says "started <time>,
  took 45 min"; a Done without a start time says "done at <time>" and no duration. Stopped:
  the start's message is edited to ⏹️ and a new "stopped" message links to it. Joining or
  taking over (editing who) posts nothing.

Webhooks can edit their own messages (PATCH .../messages/{id}) but can't add reactions, so
the ✅ is part of the message text.
"""
import os
from datetime import date, datetime

import requests
from sqlalchemy import select

import db

WEBHOOK = os.environ.get("CHORES_DISCORD_WEBHOOK_URL", "").rstrip("/")
_guild_id = None  # looked up once, for links to a message


def _who(name: str | None) -> str:
    return "someone" if not name or name == db.SYSTEM_USER else name


def _when(iso: str | None) -> str:
    """Discord's own timestamp markup: each reader sees it in their phone's time zone."""
    return f"<t:{int(datetime.fromisoformat(iso).timestamp())}:f>" if iso else ""


def _ago(iso: str | None) -> str:
    return f"<t:{int(datetime.fromisoformat(iso).timestamp())}:R>" if iso else ""


def _number(q: float) -> str:
    return f"{q:g}"


def _details(r: dict) -> list[str]:
    lines = []
    if r.get("quantity") is not None or r.get("unit"):
        q = _number(r["quantity"]) if r.get("quantity") is not None else ""
        lines.append(f"Quantity: {' '.join(p for p in (q, r.get('unit') or '') if p)}")
    if r.get("needed_by"):
        lines.append(f"Needed by: {date.fromisoformat(r['needed_by']).strftime('%a, %b %-d')}")
    if r.get("notes"):
        lines.append(f"Note: {r['notes']}")
    return lines


def request_text(r: dict) -> str:
    """The request's own message, in its current state (open, done or cancelled)."""
    head = f"**{r['chore_label']}** needs doing (asked by {_who(r['requested_by'])})"
    lines = [head, *_details(r)]
    if r["status"] == "open":
        return "🛒 " + "\n".join(lines)
    struck = [f"~~{line}~~" for line in lines]
    if r["status"] == "done":
        by = " and ".join(r["done_by"]) if r["done_by"] else _who(r["closed_by"])
        return "✅ " + "\n".join(struck) + f"\n**Done** by {by}, {_when(r['done_on'])}"
    return "❌ " + "\n".join(struck) + f"\n**Cancelled** by {_who(r['closed_by'])}, {_when(r['cancelled_on'])}"


def took_text(seconds: int | None) -> str | None:
    """"45 min", "1 h 20 min", "2 days 3 h" (None if not known)."""
    if seconds is None:
        return None
    m = max(0, seconds) // 60
    d, h, m = m // 1440, (m // 60) % 24, m % 60
    if d:
        return f"{d} day{'s' if d != 1 else ''}" + (f" {h} h" if h else "")
    if h:
        return f"{h} h" + (f" {m} min" if m else "")
    return f"{max(m, 1)} min" if seconds >= 30 else "under a minute"


def _people(names: list[str], fallback: str | None) -> str:
    return " and ".join(names) if names else _who(fallback)


def start_text(s: dict, e: dict | None = None) -> str:
    """The start's own message, in its current state (in progress, done or stopped); `e` is
    the Done that ended it, for the time it took."""
    head = f"**{s['chore_label']}** started by {_people(s['doers'], s['reporter'])}, {_when(s['started_on'])}"
    lines = [head] + ([f"Note: {s['notes']}"] if s.get("notes") else [])
    if s["status"] == "in_progress":
        return "▶️ " + "\n".join(lines)
    struck = "\n".join(f"~~{line}~~" for line in lines)
    if s["status"] == "done":
        took = took_text(e["took_seconds"]) if e else None
        return (f"✅ {struck}\n**Done**, {_when(s['ended_on'] if e is None else e['event_timestamp'])}"
                + (f", took {took}" if took else ""))
    return f"⏹️ {struck}\n**Stopped** by {_who(s['ended_by'])}, {_when(s['ended_on'])}"


def stopped_text(s: dict, link: str | None) -> str:
    return (f"⏹️ **{s['chore_label']}** stopped by {_who(s['ended_by'])} (started by "
            f"{_people(s['doers'], s['reporter'])} {_ago(s['started_on'])}, not finished)"
            + (f": {link}" if link else ""))


def done_text(e: dict, r: dict | None, link: str | None) -> str:
    """The new message for a Done (`e`, a chore event dict); `r` the request it closed. With
    a start time: when it started and how long it took; without: just when it was done."""
    by = " and ".join(e["done_by"]) if e["done_by"] else None
    head = f"✅ **{e['chore_label']}** done"
    head += f" by {by}" if by else (f" (recorded by {_who(e['reporter'])})"
                                    if e["reporter"] != db.SYSTEM_USER else "")
    took = took_text(e.get("took_seconds")) if e.get("started_on") else None
    if took:
        head += f", started {_when(e['started_on'])}, took {took}"
    else:
        head += f" at {_when(e['event_timestamp'])}"
    lines = [head]
    if e.get("notes"):
        lines.append(f"Note: {e['notes']}")
    if r is not None:
        lines.append(f"Asked for by {_who(r['requested_by'])} {_ago(r['requested_on'])}"
                     + (f": {link}" if link else ""))
    return "\n".join(lines)


def cancelled_text(r: dict, link: str | None) -> str:
    return (f"❌ **{r['chore_label']}** request cancelled by {_who(r['closed_by'])} "
            f"(asked by {_who(r['requested_by'])} {_ago(r['requested_on'])})"
            + (f": {link}" if link else ""))


def reopened_text(r: dict, deleted_by: str | None, link: str | None) -> str:
    return (f"↩️ **{r['chore_label']}** is needed again: the Done that closed it was deleted "
            f"by {_who(deleted_by)}" + (f": {link}" if link else ""))


# ---------- talking to Discord ----------

def _post(content: str) -> dict | None:
    """Post a message; returns Discord's message object (wait=true) or None."""
    if not WEBHOOK:
        return None
    try:
        r = requests.post(WEBHOOK, params={"wait": "true"}, timeout=15,
                          json={"content": content, "allowed_mentions": {"parse": []}})
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        print("chores discord post failed:", e)
        return None


def _edit(message_id: str, content: str):
    if not WEBHOOK or not message_id:
        return
    try:
        r = requests.patch(f"{WEBHOOK}/messages/{message_id}", timeout=15,
                           json={"content": content, "allowed_mentions": {"parse": []}})
        r.raise_for_status()
    except requests.RequestException as e:
        print("chores discord edit failed:", e)


def _link(message_id: str | None, channel_id: str | None) -> str | None:
    """https://discord.com/channels/<guild>/<channel>/<message>, or None if unknown."""
    global _guild_id
    if not message_id or not channel_id or not WEBHOOK:
        return None
    if _guild_id is None:
        try:
            r = requests.get(WEBHOOK, timeout=10)
            r.raise_for_status()
            _guild_id = r.json().get("guild_id")
        except (requests.RequestException, ValueError) as e:
            print("chores discord webhook lookup failed:", e)
    return f"https://discord.com/channels/{_guild_id}/{channel_id}/{message_id}" if _guild_id else None


def _stored(request_id: int, model=db.ChoreRequest) -> tuple[str | None, str | None]:
    """(message id, channel id) saved for a request (or a start, with `model`), read when the
    task runs (its own post may have finished only just before)."""
    def read(s):
        v = s.scalar(select(model.discord_message_id).where(model.id == request_id))
        return tuple(v.split("/", 1)) if v and "/" in v else (v, None)
    return db.safe_read(read, (None, None))


def _save_message(request_id: int, message: dict | None, model=db.ChoreRequest):
    if not message or "id" not in message:
        return
    # "<message id>/<channel id>": the channel is only needed for links.
    value = f"{message['id']}/{message.get('channel_id', '')}"
    try:
        with db.SessionLocal.begin() as s:
            row = s.get(model, request_id)
            if row is not None:
                row.discord_message_id = value
    except Exception as e:
        print(f"could not save the {model.__tablename__}'s Discord message id:", e)


# ---------- background tasks (chores_api.py) ----------

def requested(r: dict):
    if WEBHOOK:
        _save_message(r["id"], _post(request_text(r)))


def request_edited(r: dict):
    if WEBHOOK:
        _edit(_stored(r["id"])[0], request_text(r))


def done(e: dict, r: dict | None, s: dict | None = None):
    """A Done; `r` the request it closed and `s` the start it ended (or None)."""
    if not WEBHOOK:
        return
    link = None
    if s is not None:
        _edit(_stored(s["id"], db.ChoreStart)[0], start_text(s, e))
    if r is not None:
        mid, cid = _stored(r["id"])
        _edit(mid, request_text(r))
        link = _link(mid, cid)
    _post(done_text(e, r, link))


def started(s: dict):
    if WEBHOOK:
        _save_message(s["id"], _post(start_text(s)), db.ChoreStart)


def start_edited(s: dict, e: dict | None = None):
    if WEBHOOK:
        _edit(_stored(s["id"], db.ChoreStart)[0], start_text(s, e))


def stopped(s: dict):
    if not WEBHOOK:
        return
    mid, cid = _stored(s["id"], db.ChoreStart)
    _edit(mid, start_text(s))
    _post(stopped_text(s, _link(mid, cid)))


def cancelled(r: dict):
    if not WEBHOOK:
        return
    mid, cid = _stored(r["id"])
    _edit(mid, request_text(r))
    _post(cancelled_text(r, _link(mid, cid)))


def reopened(r: dict, deleted_by: str | None):
    if not WEBHOOK:
        return
    mid, cid = _stored(r["id"])
    _edit(mid, request_text(r))
    _post(reopened_text(r, deleted_by, _link(mid, cid)))
