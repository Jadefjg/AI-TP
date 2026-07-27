from __future__ import annotations

from backend.core.config import Settings
from backend.services.ai.constants import MODEL_PROFILE_BULK, MODEL_PROFILE_HIGH


def profile_model_chain(settings: Settings, profile: str) -> list[str]:
    if profile == MODEL_PROFILE_HIGH:
        primary = settings.resolved_high_precision_model()
        fallback = settings.resolved_fallback_model()
        return [primary, fallback]
    local = settings.ai_local_model.strip()
    if settings.ai_local_base_url.strip() and local and settings.resolved_llm_provider() == "local":
        return [local, settings.resolved_fallback_model()]
    primary = settings.resolved_bulk_model()
    fallback = settings.resolved_fallback_model()
    return [primary, fallback]
