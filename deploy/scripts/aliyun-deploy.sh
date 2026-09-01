#!/usr/bin/env bash
# AI-TP one-shot deploy helper for Alibaba Cloud ECS (or any Linux host with Docker).
#
# Usage:
#   ./deploy/scripts/aliyun-deploy.sh              # dev-like: base compose only
#   ./deploy/scripts/aliyun-deploy.sh --prod       # + compose.prod.yml (no public MySQL/Redis)
#   ./deploy/scripts/aliyun-deploy.sh --prod --small  # + compose.small.yml (2C/2G ECS)
#   If compose.shared.yml exists, it is always layered (shared MySQL/Redis).
#   ./deploy/scripts/aliyun-deploy.sh --pull       # pull images instead of --build
#
# Prerequisites:
#   - Docker Engine + Compose v2
#   - deploy/.env.docker configured (copy from deploy/.env.docker.example)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
PROD=false
SMALL=false
PULL=false

for arg in "$@"; do
  case "$arg" in
    --prod) PROD=true ;;
    --small) SMALL=true ;;
    --pull) PULL=true ;;
    -h|--help)
      sed -n '1,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy deploy/.env.docker.example and edit secrets." >&2
  exit 1
fi

COMPOSE=(docker compose -f docker-compose.yml)
if $PROD; then
  COMPOSE+=(-f compose.prod.yml)
  echo "==> Production overlay: compose.prod.yml (MySQL/Redis not published to host)"
fi
if $SMALL; then
  COMPOSE+=(-f compose.small.yml)
  echo "==> Small-ECS overlay: compose.small.yml (memory caps + CN package mirrors)"
fi
if [[ -f compose.shared.yml ]]; then
  COMPOSE+=(-f compose.shared.yml)
  echo "==> Shared middleware overlay: compose.shared.yml (common MySQL/Redis)"
fi
COMPOSE+=(--env-file "$ENV_FILE")

echo "==> Checking Docker..."
docker compose version >/dev/null

if $PULL; then
  echo "==> Pulling images..."
  "${COMPOSE[@]}" pull
  echo "==> Starting stack (pull mode)..."
  "${COMPOSE[@]}" up -d
elif $SMALL; then
  echo "==> Sequential build for small ECS (api then web; slim worker reuses api image)..."
  "${COMPOSE[@]}" build api
  "${COMPOSE[@]}" build web
  echo "==> Starting stack..."
  "${COMPOSE[@]}" up -d
else
  echo "==> Building and starting stack (first worker-tools build may take 15–30 min)..."
  "${COMPOSE[@]}" up -d --build
fi

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
echo "Deploy finished."
echo "  Web:  http://127.0.0.1:${PORT}/"
echo "  API:  http://127.0.0.1:${PORT}/api/"
echo "  Logs: docker compose --env-file ${ENV_FILE} logs -f api worker web"
echo "  Change default admin password after first login."
