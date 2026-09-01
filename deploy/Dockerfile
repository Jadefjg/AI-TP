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

# Optional Debian mirror, e.g. mirrors.aliyun.com (Aliyun ECS)
ARG DEBIAN_MIRROR=
RUN if [ -n "$DEBIAN_MIRROR" ]; then \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g; s|security.debian.org|${DEBIAN_MIRROR}|g" \
          /etc/apt/sources.list.d/debian.sources; \
      fi; \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g; s|security.debian.org|${DEBIAN_MIRROR}|g" \
          /etc/apt/sources.list; \
      fi; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
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

# Optional: PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ (Aliyun ECS)
ARG PIP_INDEX_URL=
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      pip install -e ".[mysql,redis,worker,observability]" -i "$PIP_INDEX_URL"; \
    else \
      pip install -e ".[mysql,redis,worker,observability]"; \
    fi

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
    NUCLEI_VERSION=v3.3.7 \
    K6_VERSION=v2.2.0

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      unzip \
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

# Official dl.k6.io apt repo is amd64-only; GitHub releases include linux arm64.
RUN ARCH="$(uname -m)" \
    && case "$ARCH" in \
         x86_64|amd64) KARCH=amd64 ;; \
         aarch64|arm64) KARCH=arm64 ;; \
         *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSL \
         "https://github.com/grafana/k6/releases/download/${K6_VERSION}/k6-${K6_VERSION}-linux-${KARCH}.tar.gz" \
         -o /tmp/k6.tar.gz \
    && mkdir -p /tmp/k6 \
    && tar -xzf /tmp/k6.tar.gz -C /tmp/k6 --strip-components=1 \
    && install -m 0755 /tmp/k6/k6 /usr/local/bin/k6 \
    && rm -rf /tmp/k6 /tmp/k6.tar.gz \
    && k6 version

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
