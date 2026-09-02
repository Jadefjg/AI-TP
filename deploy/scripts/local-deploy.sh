#!/usr/bin/env bash
# Local Docker one-shot deploy (Mac / Linux / WSL).
#
# Usage:
#   ./deploy/scripts/local-deploy.sh
#   ./deploy/scripts/local-deploy.sh --build
#   ./deploy/scripts/local-deploy.sh --worker-tools --build

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
BUILD=false
WORKER_TOOLS=false

for arg in "$@"; do
  case "$arg" in
    --build) BUILD=true ;;
    --worker-tools) WORKER_TOOLS=true ;;
    -h|--help)
      echo "Usage: $0 [--build] [--worker-tools]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating $ENV_FILE from deploy/.env.docker.local.example"
  cp deploy/.env.docker.local.example "$ENV_FILE"
fi

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ai-tp}"
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-isolated-middleware}"

if $WORKER_TOOLS; then
  export WORKER_DOCKER_TARGET="${WORKER_DOCKER_TARGET:-worker-tools}"
  export AI_TP_WORKER_IMAGE="${AI_TP_WORKER_IMAGE:-ai-tp-worker:local}"
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"
  echo "==> Worker-tools mode: Playwright/k6/nuclei (slow first build)"
fi

COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml --env-file "$ENV_FILE")

echo "==> Checking Docker..."
docker compose version >/dev/null

if docker ps -a --format '{{.Names}}' | grep -q '^ai-tp-local-'; then
  echo "==> Removing leftover ai-tp-local stack (port conflict with ai-tp)..."
  docker compose -p ai-tp-local down --remove-orphans 2>/dev/null || true
fi

if $BUILD; then
  echo "==> Building api + web (slim worker reuses api image unless --worker-tools)..."
  if $WORKER_TOOLS; then
    "${COMPOSE[@]}" build api worker web
  else
    "${COMPOSE[@]}" build api web
  fi
fi

echo "==> Starting stack..."
"${COMPOSE[@]}" up -d

echo "==> Waiting for API health (up to 120s)..."
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  if "${COMPOSE[@]}" exec -T api curl -fsS http://127.0.0.1:8002/ >/dev/null 2>&1; then
    echo "==> API healthy"
    break
  fi
  sleep 3
done

PORT="$(grep -E '^WEB_PUBLISH_PORT=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)"
PORT="${PORT:-8088}"

echo ""
echo "Local deploy finished."
echo "  Web:  http://127.0.0.1:${PORT}/"
echo "  API:  http://127.0.0.1:${PORT}/api/"
echo "  Logs: docker compose -p ${COMPOSE_PROJECT_NAME} -f docker-compose.yml --env-file ${ENV_FILE} logs -f api worker web"
