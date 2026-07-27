from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.entities import AiCallLog
from backend.schemas.dto import AiUsageSummaryOut


def build_ai_usage_summary(db: Session, *, organization_id: int | None) -> AiUsageSummaryOut:
    base = db.query(AiCallLog)
    if organization_id is not None:
        base = base.filter(AiCallLog.organization_id == organization_id)
    total = base.with_entities(func.count(AiCallLog.id)).scalar() or 0
    success = (
        base.filter(AiCallLog.status == "success").with_entities(func.count(AiCallLog.id)).scalar() or 0
    )
    failed = total - success
    prompt_tokens = base.with_entities(func.coalesce(func.sum(AiCallLog.prompt_tokens), 0)).scalar() or 0
    completion_tokens = base.with_entities(func.coalesce(func.sum(AiCallLog.completion_tokens), 0)).scalar() or 0
    by_module: dict[str, int] = {}
    for module_type, count in base.with_entities(AiCallLog.module_type, func.count(AiCallLog.id)).group_by(
        AiCallLog.module_type
    ):
        by_module[module_type] = count
    by_model: dict[str, int] = {}
    for model_name, count in base.with_entities(AiCallLog.model_name, func.count(AiCallLog.id)).group_by(
        AiCallLog.model_name
    ):
        by_model[model_name] = count
    return AiUsageSummaryOut(
        total_calls=total,
        success_calls=success,
        failed_calls=failed,
        total_prompt_tokens=int(prompt_tokens),
        total_completion_tokens=int(completion_tokens),
        by_module=by_module,
        by_model=by_model,
    )
