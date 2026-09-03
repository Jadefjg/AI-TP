#!/bin/sh
# Prefer MYSQL_* from env_file over compose-time DATABASE_URL defaults.
# Password is URL-encoded so special characters (@:#/ etc.) do not break the DSN.
if [ -n "${MYSQL_USER:-}" ] && [ -n "${MYSQL_PASSWORD:-}" ]; then
  DATABASE_URL="$(
    MYSQL_USER="$MYSQL_USER" MYSQL_PASSWORD="$MYSQL_PASSWORD" \
    MYSQL_HOST="${MYSQL_HOST:-mysql}" MYSQL_DATABASE="${MYSQL_DATABASE:-ai_tp}" \
    python - <<'PY'
import os
from urllib.parse import quote_plus

user = quote_plus(os.environ["MYSQL_USER"])
password = quote_plus(os.environ["MYSQL_PASSWORD"])
host = os.environ.get("MYSQL_HOST") or "mysql"
db = os.environ.get("MYSQL_DATABASE") or "ai_tp"
print(f"mysql+pymysql://{user}:{password}@{host}:3306/{db}?charset=utf8mb4")
PY
  )"
  export DATABASE_URL
fi
