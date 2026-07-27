from __future__ import annotations

import logging
import time
from typing import Any

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_MEMORY: dict[str, float] = {}
_REDIS_CLIENT: Any | None = None
_REDIS_CHECKED = False

_KEY_PREFIX = "ai-tp:oidc:state:"


def _redis_client() -> Any | None:
    global _REDIS_CLIENT, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _REDIS_CLIENT
    _REDIS_CHECKED = True
    url = (get_settings().redis_url or "").strip()
    if not url:
        return None
    try:
        import redis  # type: ignore[import-untyped]

        client = redis.from_url(url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        logger.info("OIDC state store: using Redis")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OIDC state store: Redis unavailable (%s), using in-memory", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _ttl_sec() -> int:
    return max(get_settings().oidc_state_ttl_sec, 60)


def _purge_expired_memory() -> None:
    ttl = _ttl_sec()
    now = time.time()
    expired = [k for k, ts in _MEMORY.items() if now - ts > ttl]
    for key in expired:
        _MEMORY.pop(key, None)


def store_oidc_state(state: str) -> None:
    if not state:
        raise ValueError("empty OIDC state")
    client = _redis_client()
    if client:
        client.setex(f"{_KEY_PREFIX}{state}", _ttl_sec(), "1")
        return
    _purge_expired_memory()
    _MEMORY[state] = time.time()


def consume_oidc_state(state: str) -> bool:
    if not state:
        return False
    client = _redis_client()
    if client:
        deleted = client.delete(f"{_KEY_PREFIX}{state}")
        return int(deleted) > 0
    _purge_expired_memory()
    ts = _MEMORY.pop(state, None)
    if ts is None:
        return False
    if time.time() - ts > _ttl_sec():
        return False
    return True
