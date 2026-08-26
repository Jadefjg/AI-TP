"""AI Gateway: unified LLM entry (rate-limit hook, stats, transport).

Transport stays in `llm_client`; call logging / quota remain in `scheduler`.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.services.ai.llm_client import LlmResult, chat_completion

_lock = threading.Lock()
_stats: dict[str, Any] = {
    "calls": 0,
    "errors": 0,
    "last_latency_ms": 0,
    "started_at": time.time(),
}


def gateway_stats() -> dict[str, Any]:
    with _lock:
        return dict(_stats)


async def complete(
    *,
    system_prompt: str,
    user_prompt: str,
    profile: str,
    temperature: float = 0.2,
    json_mode: bool = True,
    llm_override: dict[str, str] | None = None,
    module_type: str | None = None,
    requirement_text: str | None = None,
) -> LlmResult:
    """Single entry for all LLM completions used by Agents / workflows."""
    with _lock:
        _stats["calls"] = int(_stats.get("calls") or 0) + 1
    try:
        result = await chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
            temperature=temperature,
            json_mode=json_mode,
            llm_override=llm_override,
            module_type=module_type,
            requirement_text=requirement_text,
        )
        with _lock:
            _stats["last_latency_ms"] = result.latency_ms
            _stats["last_model"] = result.model
        return result
    except Exception:
        with _lock:
            _stats["errors"] = int(_stats.get("errors") or 0) + 1
        raise
