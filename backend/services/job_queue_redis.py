from __future__ import annotations

import logging

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "ai_tp:execution_jobs"
AI_QUEUE_KEY = "ai_tp:ai_async_jobs"


def _client():
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url:
        return None
    try:
        import redis  # type: ignore[import-untyped]

        return redis.from_url(url, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis unavailable for job queue: %s", exc)
        return None


def publish_job(job_id: int) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.lpush(QUEUE_KEY, str(job_id))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis publish job #%s failed: %s", job_id, exc)
        return False


def publish_ai_job(job_id: int) -> bool:
    client = _client()
    if not client:
        return False
    try:
        client.lpush(AI_QUEUE_KEY, str(job_id))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis publish ai job #%s failed: %s", job_id, exc)
        return False


def pop_job(timeout_sec: int = 2) -> int | None:
    client = _client()
    if not client:
        return None
    try:
        item = client.brpop(QUEUE_KEY, timeout=timeout_sec)
        if not item:
            return None
        _, raw = item
        return int(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis pop job failed: %s", exc)
        return None


def pop_ai_job(timeout_sec: int = 1) -> int | None:
    client = _client()
    if not client:
        return None
    try:
        if timeout_sec <= 0:
            raw = client.lpop(AI_QUEUE_KEY)
            return int(raw) if raw is not None else None
        item = client.brpop(AI_QUEUE_KEY, timeout=timeout_sec)
        if not item:
            return None
        _, raw = item
        return int(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis pop ai job failed: %s", exc)
        return None
