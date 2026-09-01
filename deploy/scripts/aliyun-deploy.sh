#!/usr/bin/env bash
# AI-TP one-shot deploy helper for Alibaba Cloud ECS (or any Linux host with Docker).
#
# Usage:
#   ./deploy/scripts/aliyun-deploy.sh              # 阿里云标准栈（prod + small）
#   ./deploy/scripts/aliyun-deploy.sh --worker-tools # 额外构建 Playwright/k6 worker
#   ./deploy/scripts/aliyun-deploy.sh --shared       # 接入 compose.shared.yml 公共 MySQL/Redis
#   ./deploy/scripts/aliyun-deploy.sh --pull          # pull 镜像而非 build
#
# Prerequisites:
#   - Docker Engine + Compose v2.20+（支持 include）
#   - deploy/.env.docker configured (copy from deploy/.env.docker.aliyun.example)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
WORKER_TOOLS=false
SHARED=false
PULL=false

for arg in "$@"; do
  case "$arg" in
    --worker-tools) WORKER_TOOLS=true ;;
    --shared) SHARED=true ;;
    --pull) PULL=true ;;
    --prod|--small)
      echo "Note: $arg is built into docker-compose.aliyun.yml; flag ignored." >&2
      ;;
    -h|--help)
      sed -n '1,14p' "$0"
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

COMPOSE=(docker compose -f docker-compose.aliyun.yml)
if $WORKER_TOOLS; then
  COMPOSE+=(-f compose.worker-tools.yml)
  echo "==> Worker-tools overlay: Playwright/k6/nuclei (slow first build)"
fi
if $SHARED; then
  COMPOSE+=(-f compose.shared.yml)
  echo "==> Shared middleware overlay: compose.shared.yml (external MySQL/Redis)"
fi
COMPOSE+=(--env-file "$ENV_FILE")

echo "==> Checking Docker..."
docker compose version >/dev/null

if docker ps -a --format '{{.Names}}' | grep -q '^ai-tp-local-'; then
  echo "==> Removing leftover ai-tp-local stack (port conflict with ai-tp)..."
  docker compose -p ai-tp-local down --remove-orphans 2>/dev/null || true
fi

if $PULL; then
  echo "==> Pulling images..."
  "${COMPOSE[@]}" pull
  echo "==> Starting stack (pull mode)..."
  "${COMPOSE[@]}" up -d
else
  echo "==> Building api + web (slim worker reuses api image, typically 5–15 min on ECS)..."
  "${COMPOSE[@]}" build api web
  echo "==> Starting stack..."
  "${COMPOSE[@]}" up -d
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
PORT="${PORT:-80}"

echo ""
echo "Deploy finished."
echo "  Web:  http://127.0.0.1:${PORT}/"
echo "  API:  http://127.0.0.1:${PORT}/api/"
echo "  Logs: docker compose -f docker-compose.aliyun.yml --env-file ${ENV_FILE} logs -f api worker web"
echo "  Open security group for TCP ${PORT}; change bootstrap admin password after first login."
