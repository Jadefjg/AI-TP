#!/usr/bin/env bash
# Build and push AI-TP custom images to a container registry (default: Docker Hub).
#
# Usage:
#   ./deploy/scripts/push-images.sh <registry-user> [tag]
#
# Examples:
#   ./deploy/scripts/push-images.sh mydockerhub
#   ./deploy/scripts/push-images.sh mydockerhub v0.8.0
#   AI_TP_API_IMAGE=ghcr.io/org/ai-tp-api:dev ./deploy/scripts/push-images.sh unused
#
# Requires: docker login (to Docker Hub / GHCR / etc.) before push.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

USER_NS="${1:-}"
TAG="${2:-latest}"

if [[ -z "${AI_TP_API_IMAGE:-}" || -z "${AI_TP_WEB_IMAGE:-}" ]]; then
  if [[ -z "$USER_NS" ]]; then
    echo "Usage: $0 <registry-user> [tag]" >&2
    echo "  or set AI_TP_API_IMAGE and AI_TP_WEB_IMAGE explicitly." >&2
    exit 1
  fi
  AI_TP_API_IMAGE="${USER_NS}/ai-tp-api:${TAG}"
  AI_TP_WEB_IMAGE="${USER_NS}/ai-tp-web:${TAG}"
fi

if [[ -z "${AI_TP_WORKER_IMAGE:-}" ]]; then
  if [[ -n "$USER_NS" ]]; then
    AI_TP_WORKER_IMAGE="${USER_NS}/ai-tp-worker:${TAG}"
  else
    AI_TP_WORKER_IMAGE="${AI_TP_API_IMAGE}"
  fi
fi

export AI_TP_API_IMAGE AI_TP_WORKER_IMAGE AI_TP_WEB_IMAGE
export AI_TP_WORKER_TARGET="${AI_TP_WORKER_TARGET:-worker-tools}"

ENV_FILE="${ENV_FILE:-deploy/.env.docker}"
COMPOSE=(docker compose)
if [[ -f "$ENV_FILE" ]]; then
  COMPOSE+=(--env-file "$ENV_FILE")
fi

echo "==> Building api image: ${AI_TP_API_IMAGE} (target=runtime)"
echo "==> Building worker-tools image: ${AI_TP_WORKER_IMAGE} (target=${AI_TP_WORKER_TARGET})"
echo "==> Building web image: ${AI_TP_WEB_IMAGE}"
"${COMPOSE[@]}" build api worker web

echo "==> Pushing ${AI_TP_API_IMAGE}"
docker push "${AI_TP_API_IMAGE}"

if [[ "${AI_TP_WORKER_IMAGE}" != "${AI_TP_API_IMAGE}" ]]; then
  echo "==> Pushing ${AI_TP_WORKER_IMAGE}"
  docker push "${AI_TP_WORKER_IMAGE}"
fi

echo "==> Pushing ${AI_TP_WEB_IMAGE}"
docker push "${AI_TP_WEB_IMAGE}"

echo "Done."
echo "On another machine, set the same AI_TP_*_IMAGE in deploy/.env.docker, then:"
echo "  docker compose --env-file deploy/.env.docker pull"
echo "  docker compose --env-file deploy/.env.docker up -d"
