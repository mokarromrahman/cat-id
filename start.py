"""Container entry point (see Dockerfile).

1. Wait up to DB_WAIT_SECONDS (default 30) for Postgres to accept connections.
2. If it does, run `alembic upgrade head` to create or update the tables.
3. Start the server either way: photos, labels and Discord posts must keep working when
   Postgres is down. DB writes that fail meanwhile go to inbox/_db_failed.jsonl.

If Postgres was down at startup, migrations didn't run: restart the cat-id container once
the database is back (`docker compose restart cat-id`) so a new migration gets applied.
"""
import os
import subprocess
import time

WAIT = float(os.environ.get("DB_WAIT_SECONDS", "30"))
SERVER = ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]


def wait_for_db(url: str) -> bool:
    from sqlalchemy import text

    import db

    engine = db.make_engine(url)
    deadline = time.monotonic() + WAIT
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            if time.monotonic() >= deadline:
                print(f"start: Postgres not reachable after {WAIT:.0f} s, starting without it:", e)
                return False
            time.sleep(2)
        finally:
            engine.dispose()


def main():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("start: DATABASE_URL not set, starting without a database")
    elif wait_for_db(url):
        r = subprocess.run(["alembic", "upgrade", "head"])
        if r.returncode != 0:
            print("start: migration failed (see above), starting the server anyway")
    os.execvp(SERVER[0], SERVER)


if __name__ == "__main__":
    main()
