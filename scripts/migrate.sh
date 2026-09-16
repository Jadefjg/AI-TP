#!/usr/bin/env bash
set -euo pipefail

# Historical revisions assume ORM core tables already exist. This bootstrap is
# idempotent and only creates missing tables; Alembic remains the source of
# incremental schema changes.
PYTHON_BIN="${PYTHON_BIN:-python}"
ALEMBIC_BIN="${ALEMBIC_BIN:-alembic}"
"$PYTHON_BIN" - <<'PY'
from backend.db.session import Base, engine
from backend.models import entities  # noqa: F401
Base.metadata.create_all(bind=engine)
print("[migration] base schema ensured")
PY
"$ALEMBIC_BIN" upgrade head
