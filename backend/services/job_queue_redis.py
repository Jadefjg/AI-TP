from __future__ import annotations

import logging

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "ai_tp:execution_jobs"


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
