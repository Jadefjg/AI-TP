#!/bin/sh
set -eu

. /resolve-database-url.sh

echo "[api] waiting for database..."
python - <<'PY'
import os, time, sys
url = os.environ.get("DATABASE_URL", "")
if not url or url.startswith("sqlite"):
    sys.exit(0)
# mysql+pymysql://user:pass@host:3306/db
try:
    from urllib.parse import urlparse
    import socket
    raw = url.split("://", 1)[-1]
    # strip driver extras
    if raw.startswith("pymysql://"):
        raw = raw[len("pymysql://"):]
    # user:pass@host:port/db
    hostport = raw.split("@", 1)[-1].split("/", 1)[0]
    host, _, port = hostport.partition(":")
    port = int(port or 3306)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"[api] database reachable at {host}:{port}")
                sys.exit(0)
        except OSError:
            time.sleep(2)
    print("[api] database wait timed out", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"[api] wait skipped: {exc}", file=sys.stderr)
    sys.exit(0)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  # Alembic revisions assume core ORM tables exist (projects, users, …).
  # Autogen revision 8fc22864ffb9 only adds a few tables; create_all fills the base schema.
  echo "[api] ensuring base schema (create_all)"
  python - <<'PY'
from backend.db.session import Base, engine
from backend.models import entities  # noqa: F401 — register ORM tables on Base.metadata
Base.metadata.create_all(bind=engine)
print("[api] create_all done")
PY
  echo "[api] alembic upgrade head"
  alembic upgrade head
fi

echo "[api] starting uvicorn on 0.0.0.0:8002"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8002 --workers "${UVICORN_WORKERS:-1}"
