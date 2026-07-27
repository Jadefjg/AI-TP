from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.services.ai.constants import MODEL_PROFILE_BULK, MODEL_PROFILE_HIGH
from backend.services.ai.json_utils import estimate_tokens
from backend.services.ai.llm_settings import profile_model_chain


@dataclass
class LlmResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    used_fallback: bool = False


def _profile_models(profile: str) -> list[str]:
    return profile_model_chain(get_settings(), profile)


async def _request_chat(
    *,
    base_url: str,
    api_key: str,
    resolved_model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    json_mode: bool,
    used_fallback: bool,
) -> LlmResult:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "model": resolved_model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or estimate_tokens(system_prompt + user_prompt))
    completion_tokens = int(
        usage.get("completion_tokens") or estimate_tokens(data["choices"][0]["message"]["content"])
    )
    return LlmResult(
        content=data["choices"][0]["message"]["content"],
        model=resolved_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        used_fallback=used_fallback,
    )


def _endpoint_and_key(model: str, profile: str) -> tuple[str, str, str]:
    settings = get_settings()
    resolved_model = settings.resolved_model_name(model, profile=profile)
    if profile == MODEL_PROFILE_BULK and settings.resolved_llm_provider() == "local":
        local_url = settings.ai_local_base_url.strip()
        local_model = settings.ai_local_model.strip()
        if local_url and resolved_model == local_model:
            return local_url.rstrip("/"), settings.resolved_api_key(), local_model
    return settings.resolved_base_url(), settings.resolved_api_key(), resolved_model


async def chat_completion(
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
    settings = get_settings()
    models = _profile_models(profile)
    errors: list[str] = []
    if llm_override and llm_override.get("api_key"):
        try:
            return await _request_chat(
                base_url=llm_override.get("api_base_url") or settings.openai_base_url,
                api_key=llm_override["api_key"],
                resolved_model=llm_override.get("model") or settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                json_mode=json_mode,
                used_fallback=False,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"project credential: {exc}")

    for idx, model in enumerate(models):
        base_url, api_key, resolved_model = _endpoint_and_key(model, profile)
        if not api_key:
            errors.append(f"{resolved_model}: missing API key")
            continue
        for attempt_json_mode in ([json_mode, False] if json_mode else [False]):
            try:
                return await _request_chat(
                    base_url=base_url,
                    api_key=api_key,
                    resolved_model=resolved_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    json_mode=attempt_json_mode,
                    used_fallback=idx > 0,
                )
            except Exception as exc:  # noqa: BLE001
                if attempt_json_mode and json_mode:
                    errors.append(f"{resolved_model} (json): {exc}")
                    continue
                errors.append(f"{resolved_model}: {exc}")
                break

    if not settings.llm_configured():
        return _stub_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
            module_type=module_type,
            requirement_text=requirement_text,
        )

    if settings.ai_stub_on_failure:
        stub = _stub_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
            module_type=module_type,
            requirement_text=requirement_text,
        )
        stub.used_fallback = True
        stub.model = f"{stub.model}-fallback"
        return stub

    raise RuntimeError("所有模型调用失败: " + "; ".join(errors))


def _stub_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    profile: str,
    module_type: str | None = None,
    requirement_text: str | None = None,
) -> LlmResult:
    from backend.services.ai.constants import MODULE_REQUIREMENT_REVIEW
    from backend.services.ai.stubs import build_stub_payload

    content = build_stub_payload(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        profile=profile,
        module_type=module_type,
        requirement_text=requirement_text,
    )
    model = "local-analyzer" if module_type == MODULE_REQUIREMENT_REVIEW else "stub-local"
    return LlmResult(
        content=content,
        model=model,
        prompt_tokens=estimate_tokens(system_prompt + user_prompt),
        completion_tokens=estimate_tokens(content),
        latency_ms=1,
        used_fallback=False,
    )
