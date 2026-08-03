# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      build-essential \
      default-libmysqlclient-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install -e ".[mysql,redis,worker,observability]"

RUN mkdir -p /app/data /app/data/mail_outbox

COPY deploy/scripts/entrypoint-api.sh /entrypoint-api.sh
COPY deploy/scripts/entrypoint-worker.sh /entrypoint-worker.sh
RUN chmod +x /entrypoint-api.sh /entrypoint-worker.sh

EXPOSE 8002

# Default: API. Worker overrides command in compose.
CMD ["/entrypoint-api.sh"]
