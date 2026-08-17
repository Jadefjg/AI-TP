# syntax=docker/dockerfile:1
#
# Targets:
#   runtime      — slim API / optional slim worker (no k6/nuclei/browsers)
#   worker-tools — runtime + k6 / Playwright Chromium / nuclei

FROM python:3.12-slim-bookworm AS runtime

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
      fonts-noto-cjk \
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

# ---------------------------------------------------------------------------
# Worker tools (optional heavy deps). Missing tools still skip at runtime.
# ---------------------------------------------------------------------------
FROM runtime AS worker-tools

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NUCLEI_VERSION=v3.3.7

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      unzip \
      gnupg \
      libnss3 \
      libnspr4 \
      libatk1.0-0 \
      libatk-bridge2.0-0 \
      libcups2 \
      libdrm2 \
      libdbus-1-3 \
      libxkbcommon0 \
      libxcomposite1 \
      libxdamage1 \
      libxfixes3 \
      libxrandr2 \
      libgbm1 \
      libasound2 \
      libpango-1.0-0 \
      libcairo2 \
      fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://dl.k6.io/key.gpg | gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
       > /etc/apt/sources.list.d/k6.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends k6 \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH="$(uname -m)" \
    && case "$ARCH" in \
         x86_64|amd64) NARCH=amd64 ;; \
         aarch64|arm64) NARCH=arm64 ;; \
         *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSL \
         "https://github.com/projectdiscovery/nuclei/releases/download/${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION#v}_linux_${NARCH}.zip" \
         -o /tmp/nuclei.zip \
    && unzip -o /tmp/nuclei.zip -d /tmp/nuclei \
    && install -m 0755 /tmp/nuclei/nuclei /usr/local/bin/nuclei \
    && rm -rf /tmp/nuclei /tmp/nuclei.zip \
    && nuclei -version

RUN mkdir -p /ms-playwright \
    && python -m playwright install chromium \
    && k6 version \
    && python -c "import playwright; print('playwright ok')"

CMD ["/entrypoint-worker.sh"]
