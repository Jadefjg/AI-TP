from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.entities import PromptFeedback, PromptTemplate
from backend.services.ai.prompt_service import bump_template_version, get_active_template


def record_feedback(
    db: Session,
    *,
    project_id: int | None,
    module_type: str,
    source_type: str,
    source_id: int | None,
    original_text: str,
    corrected_text: str,
    prompt_template_id: int | None = None,
    note: str | None = None,
) -> PromptFeedback:
    row = PromptFeedback(
        project_id=project_id,
        module_type=module_type,
        source_type=source_type,
        source_id=source_id,
        original_text=original_text[:50000],
        corrected_text=corrected_text[:50000],
        prompt_template_id=prompt_template_id,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_optimization_suggestions(db: Session, *, module_type: str, limit: int = 20) -> dict:
    rows = (
        db.query(PromptFeedback)
        .filter(PromptFeedback.module_type == module_type, PromptFeedback.applied.is_(False))
        .order_by(PromptFeedback.id.desc())
        .limit(limit)
        .all()
    )
    examples = []
    for row in rows:
        examples.append(
            {
                "feedback_id": row.id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "original_preview": row.original_text[:200],
                "corrected_preview": row.corrected_text[:200],
                "note": row.note,
            }
        )
    active = get_active_template(db, module_type)
    suggestion_block = "\n\n".join(
        f"【人工修正样例 {i + 1}】\n原：{e['original_preview']}\n改：{e['corrected_preview']}"
        for i, e in enumerate(examples[:5])
    )
    proposed_append = ""
    if suggestion_block:
        proposed_append = (
            "\n\n【平台沉淀的人工修正样例 - 生成时请参考】\n"
            + suggestion_block
            + "\n【约束】优先吸收上述修正风格，避免重复已知问题。"
        )
    return {
        "module_type": module_type,
        "feedback_count": len(rows),
        "active_template_id": active.id if active else None,
        "active_template_version": active.version if active else None,
        "proposed_append": proposed_append,
        "examples": examples,
    }


def apply_suggestions_to_template(db: Session, *, module_type: str, mark_applied: bool = True) -> PromptTemplate:
    active = get_active_template(db, module_type)
    if not active:
        raise ValueError(f"no active template for module_type={module_type}")
    suggestion = build_optimization_suggestions(db, module_type=module_type)
    append = suggestion.get("proposed_append") or ""
    if not append.strip():
        raise ValueError("暂无可应用的修正样例")
    new_content = active.content.rstrip() + append
    new_template = bump_template_version(db, active, content=new_content, is_active=True)
    if mark_applied:
        db.query(PromptFeedback).filter(
            PromptFeedback.module_type == module_type,
            PromptFeedback.applied.is_(False),
        ).update({"applied": True}, synchronize_session=False)
        db.commit()
    return new_template
