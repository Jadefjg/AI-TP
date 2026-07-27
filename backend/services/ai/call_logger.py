from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.entities import AiCallLog
from backend.services.ai.llm_client import LlmResult


def log_ai_call(
    db: Session,
    *,
    project_id: int | None,
    organization_id: int | None = None,
    user_id: int | None = None,
    module_type: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str,
    used_fallback: bool = False,
    error_detail: str | None = None,
    prompt_template_id: int | None = None,
) -> AiCallLog:
    row = AiCallLog(
        project_id=project_id,
        organization_id=organization_id,
        user_id=user_id,
        module_type=module_type,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=status,
        used_fallback=used_fallback,
        error_detail=error_detail,
        prompt_template_id=prompt_template_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
