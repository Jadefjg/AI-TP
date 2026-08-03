#!/bin/sh
set -eu

echo "[worker] waiting for database..."
python - <<'PY'
import os, time, sys
url = os.environ.get("DATABASE_URL", "")
if not url or url.startswith("sqlite"):
    sys.exit(0)
try:
    import socket
    raw = url.split("://", 1)[-1]
    if raw.startswith("pymysql://"):
        raw = raw[len("pymysql://"):]
    hostport = raw.split("@", 1)[-1].split("/", 1)[0]
    host, _, port = hostport.partition(":")
    port = int(port or 3306)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"[worker] database reachable at {host}:{port}")
                sys.exit(0)
        except OSError:
            time.sleep(2)
    print("[worker] database wait timed out", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"[worker] wait skipped: {exc}", file=sys.stderr)
    sys.exit(0)
PY

if [ -n "${REDIS_URL:-}" ]; then
  echo "[worker] waiting for redis..."
  python - <<'PY'
import os, time, sys, socket
from urllib.parse import urlparse
u = urlparse(os.environ["REDIS_URL"])
host = u.hostname or "redis"
port = u.port or 6379
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[worker] redis reachable at {host}:{port}")
            sys.exit(0)
    except OSError:
        time.sleep(2)
print("[worker] redis wait timed out", file=sys.stderr)
sys.exit(1)
PY
fi

echo "[worker] starting backend.worker"
exec python -m backend.worker
