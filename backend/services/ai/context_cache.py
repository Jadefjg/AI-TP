from __future__ import annotations

import json
import time
from typing import Any

from backend.core.config import get_settings

_MEMORY: dict[str, tuple[float, str]] = {}
_REDIS_CLIENT: Any | None = None
_REDIS_CHECKED = False


def _redis():
    global _REDIS_CLIENT, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _REDIS_CLIENT
    _REDIS_CHECKED = True
    url = get_settings().redis_url.strip()
    if not url:
        return None
    try:
        import redis  # type: ignore[import-untyped]

        _REDIS_CLIENT = redis.from_url(url, decode_responses=True)
        _REDIS_CLIENT.ping()
    except Exception:  # noqa: BLE001
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _key(project_id: int, module_type: str) -> str:
    return f"ai-tp:ctx:{project_id}:{module_type}"


def get_context(project_id: int, module_type: str) -> str | None:
    key = _key(project_id, module_type)
    client = _redis()
    if client:
        return client.get(key)
    item = _MEMORY.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at < time.time():
        _MEMORY.pop(key, None)
        return None
    return value


def set_context(project_id: int, module_type: str, content: str) -> None:
    ttl = max(get_settings().ai_context_ttl_sec, 60)
    key = _key(project_id, module_type)
    client = _redis()
    if client:
        client.setex(key, ttl, content)
        return
    _MEMORY[key] = (time.time() + ttl, content)


def append_context(project_id: int, module_type: str, snippet: str) -> None:
    existing = get_context(project_id, module_type) or ""
    merged = (existing + "\n\n" + snippet).strip()[-20000:]
    set_context(project_id, module_type, merged)


def context_as_dict(project_id: int, module_type: str) -> dict[str, Any]:
    raw = get_context(project_id, module_type)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"text": raw}
    except json.JSONDecodeError:
        return {"text": raw}
