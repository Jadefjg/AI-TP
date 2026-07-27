from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.entities import AiArtifact, AiCallLog, PromptFeedback, PromptTemplate, RequirementReview
from backend.services.ai.builtin_prompts import BUILTIN_PROMPT_SPECS
from backend.services.ai.constants import AI_MODULES, MODULE_REQUIRED_PLACEHOLDERS

_PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def render_prompt(template: str, variables: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return variables.get(key, "")

    return _PLACEHOLDER.sub(_replace, template)


def get_active_template(db: Session, module_type: str) -> PromptTemplate | None:
    return (
        db.query(PromptTemplate)
        .filter(PromptTemplate.module_type == module_type, PromptTemplate.is_active.is_(True))
        .order_by(PromptTemplate.version.desc(), PromptTemplate.id.desc())
        .first()
    )


def _builtin_prompt_content(module_type: str) -> str | None:
    for mod, _name, _profile, content in BUILTIN_PROMPT_SPECS:
        if mod == module_type:
            return content
    return None


def _template_has_required_placeholders(content: str, module_type: str) -> bool:
    required = MODULE_REQUIRED_PLACEHOLDERS.get(module_type, ())
    if not required:
        return True
    return all(f"{{{{{name}}}}}" in content for name in required)


def resolve_prompt_content(db: Session, module_type: str, variables: dict[str, str]) -> tuple[str, int | None]:
    row = get_active_template(db, module_type)
    if row and _template_has_required_placeholders(row.content, module_type):
        return render_prompt(row.content, variables), row.id
    builtin = _builtin_prompt_content(module_type)
    if builtin is None:
        raise ValueError(f"unknown module_type: {module_type}")
    return render_prompt(builtin, variables), row.id if row else None


def seed_builtin_templates(db: Session) -> None:
    changed = False
    for module_type, name, model_profile, content in BUILTIN_PROMPT_SPECS:
        exists = (
            db.query(PromptTemplate)
            .filter(PromptTemplate.module_type == module_type, PromptTemplate.name == name)
            .order_by(PromptTemplate.id.asc())
            .first()
        )
        if exists:
            continue
        db.add(
            PromptTemplate(
                module_type=module_type,
                name=name,
                content=content,
                model_profile=model_profile,
                version=1,
                is_active=True,
            )
        )
        changed = True
    if changed:
        db.commit()


def bump_template_version(db: Session, template: PromptTemplate, *, content: str | None = None, is_active: bool | None = None) -> PromptTemplate:
    template.is_active = False
    template.updated_at = datetime.now(timezone.utc)
    db.add(template)
    db.flush()
    new_row = PromptTemplate(
        module_type=template.module_type,
        name=template.name,
        content=content if content is not None else template.content,
        model_profile=template.model_profile,
        version=template.version + 1,
        is_active=True if is_active is None else is_active,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def list_module_types() -> list[str]:
    return list(AI_MODULES)


def delete_prompt_template(db: Session, template: PromptTemplate) -> None:
    """Remove a template version; historical rows keep FK nulled."""
    tid = template.id
    module_type = template.module_type
    was_active = template.is_active

    db.query(AiCallLog).filter(AiCallLog.prompt_template_id == tid).update(
        {AiCallLog.prompt_template_id: None},
        synchronize_session=False,
    )
    db.query(RequirementReview).filter(RequirementReview.prompt_template_id == tid).update(
        {RequirementReview.prompt_template_id: None},
        synchronize_session=False,
    )
    db.query(PromptFeedback).filter(PromptFeedback.prompt_template_id == tid).update(
        {PromptFeedback.prompt_template_id: None},
        synchronize_session=False,
    )
    db.query(AiArtifact).filter(AiArtifact.prompt_template_id == tid).update(
        {AiArtifact.prompt_template_id: None},
        synchronize_session=False,
    )

    db.delete(template)
    db.flush()

    if was_active:
        replacement = (
            db.query(PromptTemplate)
            .filter(PromptTemplate.module_type == module_type)
            .order_by(PromptTemplate.version.desc(), PromptTemplate.id.desc())
            .first()
        )
        if replacement:
            db.query(PromptTemplate).filter(
                PromptTemplate.module_type == module_type,
                PromptTemplate.id != replacement.id,
                PromptTemplate.is_active.is_(True),
            ).update({"is_active": False}, synchronize_session=False)
            replacement.is_active = True
            db.add(replacement)
