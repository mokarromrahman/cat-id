"""Retry DB writes that failed while Postgres was down.

Each line of inbox/_db_failed.jsonl is one write that the server couldn't save
({"kind", "payload", "error", "failed_at"}). This runs each one again, in order, through the
same writer the server used, and keeps only the lines that still fail.

Run it inside the server container once the database is back:
    docker compose exec cat-id python replay_db_failed.py
    docker compose exec cat-id python replay_db_failed.py --dry-run   # just list them
"""
import fcntl
import json
import sys

import db  # the writers live in db.py, so this doesn't load the model or the server


def main(dry_run: bool):
    path = db.FAILED_FILE
    if not path.exists():
        print(f"nothing to replay: {path} does not exist")
        return
    with open(path, "r+") as f:
        # Same lock the server takes when appending, so no line is lost while this runs.
        fcntl.flock(f, fcntl.LOCK_EX)
        lines = [line for line in f.read().splitlines() if line.strip()]
        kept, done = [], 0
        for line in lines:
            entry = json.loads(line)
            kind = entry["kind"]
            if dry_run:
                print(f"{entry['failed_at']}  {kind}  {entry['error']}")
                continue
            if kind not in db.WRITERS:
                print(f"skipping unknown kind '{kind}', kept in the file")
                kept.append(line)
                continue
            try:
                db.run_writer(kind, entry["payload"])
                done += 1
            except Exception as e:
                print(f"still failing: {kind}: {type(e).__name__}: {e}")
                kept.append(line)
        if dry_run:
            print(f"{len(lines)} waiting")
            return
        f.seek(0)
        f.truncate()
        f.write("".join(line + "\n" for line in kept))
    print(f"replayed {done}, {len(kept)} still waiting")


if __name__ == "__main__":
    main("--dry-run" in sys.argv[1:])
