#!/usr/bin/env bash
# AI-TP one-shot deploy for Alibaba Cloud ECS.
#
# This host already has /opt/shared-infra (shared-mysql / shared-redis).
# Default mode REUSES them — it will NOT start another MySQL/Redis in the ai-tp project.
#
# Usage:
#   ./deploy/scripts/aliyun-deploy.sh              # 复用 shared-infra，不重建镜像
#   ./deploy/scripts/aliyun-deploy.sh --build      # 仅构建 api/web 后 up（2G 请先停其他栈）
#   ./deploy/scripts/aliyun-deploy.sh --worker-tools
#   ./deploy/scripts/aliyun-deploy.sh --isolated   # 仅当没有 shared-infra 时才自带 MySQL/Redis
#   ./deploy/scripts/aliyun-deploy.sh --pull
#
# Prerequisites:
#   - Docker Engine + Compose v2.24+（overlay 使用 !reset）
#   - deploy/.env.docker configured (copy from deploy/.env.docker.aliyun.example)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
WORKER_TOOLS=false
# Default: share middleware so compose does not spawn a second MySQL/Redis.
SHARED=true
ISOLATED=false
PULL=false
BUILD=false

for arg in "$@"; do
  case "$arg" in
    --worker-tools) WORKER_TOOLS=true ;;
    --shared) SHARED=true ;;
    --isolated) ISOLATED=true; SHARED=false ;;
    --build) BUILD=true ;;
    --pull) PULL=true ;;
    --prod|--small)
      echo "Note: $arg is built into docker-compose.aliyun.yml; flag ignored." >&2
      ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy deploy/.env.docker.aliyun.example and edit secrets." >&2
  exit 1
fi

shared_ready() {
  docker network inspect shared-infra >/dev/null 2>&1 || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' shared-mysql 2>/dev/null || true)" == "true" ]] || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' shared-redis 2>/dev/null || true)" == "true" ]] || return 1
}

if $ISOLATED; then
  if shared_ready; then
    echo "Refusing --isolated: shared-mysql/shared-redis already run on this host." >&2
    echo "Reuse them with: $0   (default, no extra MySQL/Redis)" >&2
    exit 1
  fi
  SHARED=false
elif ! shared_ready; then
  echo "shared-infra not running; falling back to in-stack MySQL/Redis." >&2
  SHARED=false
fi

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ai-tp}"

COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml -f docker-compose.aliyun.yml)
if $WORKER_TOOLS; then
  COMPOSE+=(-f compose.worker-tools.yml)
  echo "==> Worker-tools overlay: Playwright/k6/nuclei (slow first build)"
fi
if $SHARED; then
  COMPOSE+=(-f compose.shared.yml)
  echo "==> Reusing shared-mysql / shared-redis (no extra DB containers)"
fi
COMPOSE+=(--env-file "$ENV_FILE")

echo "==> Checking Docker..."
docker compose version >/dev/null

if docker ps -a --format '{{.Names}}' | grep -q '^ai-tp-local-'; then
  echo "==> Removing leftover ai-tp-local stack (duplicate of ai-tp)..."
  docker compose -p ai-tp-local down --remove-orphans 2>/dev/null || true
fi

if $SHARED; then
  # Drop in-project MySQL/Redis if a previous isolated deploy created them.
  for name in ai-tp-mysql-1 ai-tp-redis-1; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
      echo "==> Removing leftover $name (middleware already provided by shared-infra)"
      docker rm -f "$name" >/dev/null
    fi
  done
fi

if $PULL; then
  echo "==> Pulling images..."
  "${COMPOSE[@]}" pull
  echo "==> Starting stack (no recreate if already running)..."
  "${COMPOSE[@]}" up -d --remove-orphans --no-recreate
elif $BUILD; then
  echo "==> Building api + web (slim worker reuses api image)..."
  "${COMPOSE[@]}" build api web
  echo "==> Starting stack..."
  "${COMPOSE[@]}" up -d --remove-orphans
else
  echo "==> Starting stack (reuse images; do not recreate healthy containers)..."
  "${COMPOSE[@]}" up -d --remove-orphans --no-recreate
fi

echo "==> Waiting for API health (up to 120s)..."
deadline=$((SECONDS + 120))
healthy=false
while (( SECONDS < deadline )); do
  if "${COMPOSE[@]}" exec -T api curl -fsS http://127.0.0.1:8002/ >/dev/null 2>&1; then
    echo "==> API healthy"
    healthy=true
    break
  fi
  sleep 3
done
if ! $healthy; then
  echo "==> API not healthy yet; check: ${COMPOSE[*]} logs api" >&2
fi

PORT="$(grep -E '^WEB_PUBLISH_PORT=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)"
PORT="${PORT:-80}"

echo ""
echo "Deploy finished (project=${COMPOSE_PROJECT_NAME})."
echo "  Web:  http://127.0.0.1:${PORT}/"
echo "  API:  http://127.0.0.1:${PORT}/api/"
echo "  Logs: docker compose -p ${COMPOSE_PROJECT_NAME} -f docker-compose.yml -f docker-compose.aliyun.yml --env-file ${ENV_FILE} logs -f api worker web"
echo "  Open security group for TCP ${PORT}; change bootstrap admin password after first login."
echo "  Running AI-TP containers:"
docker ps --filter "name=ai-tp-" --format '  {{.Names}}  {{.Status}}  {{.Ports}}'
