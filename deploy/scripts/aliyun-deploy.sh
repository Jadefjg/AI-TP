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
#   - Docker Engine + Compose v2.24+（depends_on.required: false）
#   - deploy/.env.docker configured (copy from deploy/.env.docker.aliyun.example)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
WORKER_TOOLS=false
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
      echo "Note: $arg is configured via deploy/.env.docker; flag ignored." >&2
      ;;
    -h|--help)
      sed -n '1,22p' "$0"
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

if $SHARED; then
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-shared-middleware}"
  export MYSQL_HOST="${MYSQL_HOST:-shared-mysql}"
  export REDIS_URL="${REDIS_URL:-redis://shared-redis:6379/0}"
  export API_MEM_LIMIT="${API_MEM_LIMIT:-320m}"
  export WORKER_MEM_LIMIT="${WORKER_MEM_LIMIT:-256m}"
  export WEB_MEM_LIMIT="${WEB_MEM_LIMIT:-48m}"
  echo "==> Reusing shared-mysql / shared-redis (no extra DB containers)"
else
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-isolated-middleware}"
  export MYSQL_HOST="${MYSQL_HOST:-mysql}"
  export REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
  export MYSQL_IMAGE="${MYSQL_IMAGE:-mysql:8.0}"
  export MYSQL_INNODB_BUFFER_POOL_SIZE="${MYSQL_INNODB_BUFFER_POOL_SIZE:-96M}"
  export MYSQL_INNODB_LOG_BUFFER_SIZE="${MYSQL_INNODB_LOG_BUFFER_SIZE:-8M}"
  export MYSQL_PERFORMANCE_SCHEMA="${MYSQL_PERFORMANCE_SCHEMA:-OFF}"
  export MYSQL_MAX_CONNECTIONS="${MYSQL_MAX_CONNECTIONS:-50}"
  export MYSQL_MEM_LIMIT="${MYSQL_MEM_LIMIT:-256m}"
  export REDIS_MEM_LIMIT="${REDIS_MEM_LIMIT:-64m}"
  export API_MEM_LIMIT="${API_MEM_LIMIT:-384m}"
  export WORKER_MEM_LIMIT="${WORKER_MEM_LIMIT:-384m}"
  export WEB_MEM_LIMIT="${WEB_MEM_LIMIT:-64m}"
  echo "==> In-stack MySQL/Redis (isolated-middleware profile)"
fi

if $WORKER_TOOLS; then
  export WORKER_DOCKER_TARGET="${WORKER_DOCKER_TARGET:-worker-tools}"
  export AI_TP_WORKER_IMAGE="${AI_TP_WORKER_IMAGE:-ai-tp-worker:local}"
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"
  echo "==> Worker-tools mode: Playwright/k6/nuclei (slow first build)"
fi

COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml --env-file "$ENV_FILE")

ensure_shared_network() {
  if ! docker network inspect shared-infra >/dev/null 2>&1; then
    echo "shared-infra network missing; create /opt/shared-infra first or use --isolated" >&2
    exit 1
  fi
}

connect_shared_network() {
  # Belt-and-suspenders if an old container was started without the compose network.
  local svc cid
  for svc in api worker; do
    cid="$("${COMPOSE[@]}" ps -q "$svc" 2>/dev/null || true)"
    [[ -n "$cid" ]] || continue
    if docker inspect -f '{{json .NetworkSettings.Networks}}' "$cid" | grep -q '"shared-infra"'; then
      continue
    fi
    echo "==> Connecting $svc to shared-infra"
    docker network connect shared-infra "$cid" || true
  done
}

start_stack() {
  local recreate_flags=("$@")
  if $SHARED; then
    ensure_shared_network
    # Start API first so it joins shared-infra before worker/web wait on health.
    echo "==> Starting api (shared-infra DB)..."
    "${COMPOSE[@]}" up -d --no-deps --remove-orphans "${recreate_flags[@]}" api
    connect_shared_network
    echo "==> Waiting for API health before starting worker/web (up to 180s)..."
    local deadline=$((SECONDS + 180))
    local healthy=false
    while (( SECONDS < deadline )); do
      if "${COMPOSE[@]}" exec -T api curl -fsS http://127.0.0.1:8002/ >/dev/null 2>&1; then
        echo "==> API healthy"
        healthy=true
        break
      fi
      sleep 3
    done
    if ! $healthy; then
      echo "==> API not healthy; dumping logs:" >&2
      "${COMPOSE[@]}" logs --tail=80 api >&2 || true
      exit 1
    fi
    echo "==> Starting worker + web..."
    "${COMPOSE[@]}" up -d --remove-orphans "${recreate_flags[@]}"
    connect_shared_network
  else
    echo "==> Starting stack..."
    "${COMPOSE[@]}" up -d --remove-orphans "${recreate_flags[@]}"
  fi
}

echo "==> Checking Docker..."
docker compose version >/dev/null

if docker ps -a --format '{{.Names}}' | grep -q '^ai-tp-local-'; then
  echo "==> Removing leftover ai-tp-local stack (duplicate of ai-tp)..."
  docker compose -p ai-tp-local down --remove-orphans 2>/dev/null || true
fi

if $SHARED; then
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
  start_stack --no-recreate
elif $BUILD; then
  echo "==> Building api + web (slim worker reuses api image unless --worker-tools)..."
  if $WORKER_TOOLS; then
    "${COMPOSE[@]}" build api worker web
  else
    "${COMPOSE[@]}" build api web
  fi
  start_stack
else
  start_stack --no-recreate
fi

echo "==> Waiting for API health (final check, up to 60s)..."
deadline=$((SECONDS + 60))
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
echo "  Logs: docker compose -p ${COMPOSE_PROJECT_NAME} -f docker-compose.yml --env-file ${ENV_FILE} logs -f api worker web"
echo "  Open security group for TCP ${PORT}; change bootstrap admin password after first login."
echo "  Running AI-TP containers:"
docker ps --filter "name=ai-tp-" --format '  {{.Names}}  {{.Status}}  {{.Ports}}'
