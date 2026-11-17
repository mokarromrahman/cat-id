"""Push changed Postgres rows to a Databricks Unity Catalog Volume as Parquet, for Auto Loader.

Runs as the `exporter` service in docker-compose.yml (`--loop`, every EXPORT_INTERVAL_SECONDS,
default 3600). By hand, in the container:
    docker compose exec exporter python export_databricks.py              # one run
    docker compose exec exporter python export_databricks.py --dry-run /app/inbox/_export_test
The dry run writes the files to that folder instead of uploading and doesn't move the
watermarks, so it can be repeated.

Each run, for every table in db.py (except db.NOT_EXPORTED):
  - rows with modified_on after the table's watermark (export_state.exported_through), plus
  - rows deleted since then (deleted_row, turned back into typed rows by Postgres), flagged
    _deleted = true,
in one REPEATABLE READ snapshot, written to
    <DATABRICKS_VOLUME_PATH>/<table>/<table>_<YYYYmmddTHHMMSSffffff>Z.parquet
and uploaded with the Files API. Extra columns: _deleted, _deleted_at, _change_on (modified_on,
or the delete time for a deleted row: what silver orders changes by) and _exported_at.

The watermark moves to (run start - OVERLAP) only after that table's upload succeeds. modified_on
is the time a transaction *started*, so a transaction still open when the run starts can commit
rows dated before it; the overlap re-reads those minutes next time. Rows inside the overlap are
sent twice; silver keeps one. A table with nothing new uploads nothing. First run (no watermark):
everything, and a file even for an empty table. To resend a table from scratch: DELETE FROM export_state WHERE table_name = '...'.

Needs DATABASE_URL, DATABRICKS_HOST (https://<workspace>.cloud.databricks.com), DATABRICKS_TOKEN
(a personal access token). Without the Databricks settings it does nothing.
"""
import argparse
import io
import os
import sys
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from sqlalchemy import (
    REAL, Boolean, Date, DateTime, Float, Integer, Numeric, String, Time, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

import db

HOST = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
TOKEN = os.environ.get("DATABRICKS_TOKEN", "").strip()
VOLUME = os.environ.get("DATABRICKS_VOLUME_PATH", "/Volumes/cat_id/bronze/landing").rstrip("/")
INTERVAL = float(os.environ.get("EXPORT_INTERVAL_SECONDS", "3600"))
RETRY_SECONDS = 300   # after a failed run (failed tables kept their watermark)
OVERLAP = timedelta(minutes=5)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
TIMEOUT = 120

EXTRA_FIELDS = [
    pa.field("_deleted", pa.bool_()),
    pa.field("_deleted_at", pa.timestamp("us", tz="UTC")),
    pa.field("_change_on", pa.timestamp("us", tz="UTC")),
    pa.field("_exported_at", pa.timestamp("us", tz="UTC")),
]


def tables():
    return [t for t in db.Base.metadata.sorted_tables if t.name not in db.NOT_EXPORTED]


def arrow_type(column):
    """The Parquet type for a column. Times go out as "HH:MM:SS" text: Spark has no TIME type."""
    t = column.type
    if isinstance(t, ARRAY):
        return pa.list_(pa.string())
    if isinstance(t, Boolean):
        return pa.bool_()
    if isinstance(t, Integer):
        return pa.int64()
    if isinstance(t, (REAL, Float)):
        return pa.float32() if isinstance(t, REAL) else pa.float64()
    if isinstance(t, Numeric):
        return pa.decimal128(t.precision or 38, t.scale or 0)
    if isinstance(t, DateTime):
        return pa.timestamp("us", tz="UTC")
    if isinstance(t, Date):
        return pa.date32()
    if isinstance(t, (Time, JSONB, String)):
        return pa.string()
    raise TypeError(f"{column.table.name}.{column.name}: no Parquet type for {t!r}")


def schema(table):
    return pa.schema([pa.field(c.name, arrow_type(c)) for c in table.columns] + EXTRA_FIELDS)


def watermarks(conn) -> dict:
    return dict(conn.execute(text("SELECT table_name, exported_through FROM export_state")).all())


def read_changes(conn, table, since: datetime, run_at: datetime) -> list[dict]:
    """Rows changed after `since`, then rows deleted after it, as dicts in schema() order."""
    name = table.name   # from db.py's metadata, not user input
    live = conn.execute(text(
        f'SELECT *, false AS _deleted, NULL::timestamptz AS _deleted_at, '
        f'modified_on AS _change_on FROM "{name}" WHERE modified_on > :since ORDER BY id'),
        {"since": since}).mappings().all()
    gone = conn.execute(text(
        f'SELECT (jsonb_populate_record(NULL::"{name}", d.row_data)).*, true AS _deleted, '
        f'd.deleted_on AS _deleted_at, d.deleted_on AS _change_on FROM deleted_row d '
        f'WHERE d.table_name = :name AND d.modified_on > :since ORDER BY d.id'),
        {"since": since, "name": name}).mappings().all()
    times = [c.name for c in table.columns if isinstance(c.type, Time)]
    rows = []
    for r in [*live, *gone]:
        row = dict(r)
        for c in times:
            if row[c] is not None:
                row[c] = row[c].isoformat()
        row["_exported_at"] = run_at
        rows.append(row)
    return rows


def to_parquet(table, rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows, schema=schema(table)), buf, compression="snappy")
    return buf.getvalue()


class Volume:
    """Uploads with the Databricks Files API (outbound HTTPS only)."""

    def __init__(self, host: str, token: str):
        self.host = host
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"
        self.made: set[str] = set()

    def _url(self, kind: str, path: str) -> str:
        return f"{self.host}/api/2.0/fs/{kind}{quote(path)}"

    def mkdir(self, path: str):
        if path not in self.made:
            self.http.put(self._url("directories", path), timeout=TIMEOUT).raise_for_status()
            self.made.add(path)

    def put(self, path: str, data: bytes):
        self.mkdir(path.rsplit("/", 1)[0])
        r = self.http.put(self._url("files", path), params={"overwrite": "false"}, data=data,
                          headers={"Content-Type": "application/octet-stream"}, timeout=TIMEOUT)
        if not r.ok:
            raise RuntimeError(f"upload {path}: HTTP {r.status_code} {r.text[:300]}")


def save_watermark(table: str, through: datetime, run_at: datetime, file: str | None, count: int):
    with db.engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO export_state (table_name, exported_through, last_run_on, last_file, "
            "last_row_count) VALUES (:t, :through, :run_at, :file, :count) "
            "ON CONFLICT (table_name) DO UPDATE SET exported_through = EXCLUDED.exported_through, "
            "last_run_on = EXCLUDED.last_run_on, last_file = EXCLUDED.last_file, "
            "last_row_count = EXCLUDED.last_row_count"),
            {"t": table, "through": through, "run_at": run_at, "file": file, "count": count})


def run_once(dry_run: Path | None = None) -> bool:
    """One export of every table. True if every table was sent (or had nothing new)."""
    # One snapshot for all tables, so a picture and its event are read at the same moment.
    with db.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            run_at = conn.execute(text("SELECT now()")).scalar_one()
            marks = watermarks(conn)
            batches = [(t, marks.get(t.name), read_changes(conn, t, marks.get(t.name, EPOCH), run_at))
                       for t in tables()]

    stamp = run_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "Z"
    volume = None if dry_run else Volume(HOST, TOKEN)
    sent, failed = [], []
    for table, old_mark, rows in batches:
        # Never move a watermark backwards (e.g. a clock change on the DB host).
        through = max(run_at - OVERLAP, old_mark) if old_mark else run_at - OVERLAP
        path = None
        try:
            # First run: send even an empty table, so every table gets a folder (Auto Loader
            # reads the schema from the file) and a bronze/silver table in Databricks.
            if rows or old_mark is None:
                data = to_parquet(table, rows)
                path = f"{VOLUME}/{table.name}/{table.name}_{stamp}.parquet"
                if dry_run:
                    out = dry_run / table.name / f"{table.name}_{stamp}.parquet"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                    path = str(out)
                else:
                    volume.put(path, data)
                sent.append(f"{table.name} {len(rows)}")
            if not dry_run:
                save_watermark(table.name, through, run_at, path, len(rows))
        except Exception as e:
            failed.append(table.name)
            print(f"export: {table.name} failed, will retry: {e}", flush=True)
    summary = ", ".join(sent) if sent else "nothing new"
    if failed:
        summary += f"; FAILED: {', '.join(failed)}"
    print(f"export {stamp}{' (dry run)' if dry_run else ''}: {summary}", flush=True)
    return not failed


def configured() -> bool:
    return bool(HOST and TOKEN and db.engine is not None)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--loop", action="store_true", help="run every EXPORT_INTERVAL_SECONDS")
    ap.add_argument("--dry-run", type=Path, metavar="DIR",
                    help="write the files to DIR instead of uploading; watermarks don't move")
    args = ap.parse_args()

    if args.dry_run:
        if db.engine is None:
            sys.exit("export: DATABASE_URL not set")
        sys.exit(0 if run_once(args.dry_run) else 1)
    if not configured():
        print("export: DATABRICKS_HOST, DATABRICKS_TOKEN or DATABASE_URL not set; not exporting",
              flush=True)
        if args.loop:   # stay up quietly so `restart: unless-stopped` doesn't loop
            while True:
                _time.sleep(86400)
        return
    if not args.loop:
        sys.exit(0 if run_once() else 1)
    while True:
        started = _time.monotonic()
        try:
            ok = run_once()
        except Exception as e:   # DB down or not migrated yet, network down
            print(f"export: run failed: {e}", flush=True)
            ok = False
        wait = INTERVAL if ok else min(INTERVAL, RETRY_SECONDS)
        _time.sleep(max(60.0, wait - (_time.monotonic() - started)))


if __name__ == "__main__":
    main()
