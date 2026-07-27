"""Prompt template resolution safeguards."""

from backend.models.entities import PromptTemplate
from backend.services.ai.constants import MODULE_REQUIREMENT_REVIEW
from backend.services.ai.prompt_service import resolve_prompt_content


def test_resolve_prompt_falls_back_when_active_template_invalid(db):
    row = PromptTemplate(
        module_type=MODULE_REQUIREMENT_REVIEW,
        name="broken",
        content="无效模板，没有变量占位符",
        model_profile="high_precision",
        version=99,
        is_active=True,
    )
    db.add(row)
    db.commit()

    text, template_id = resolve_prompt_content(
        db,
        MODULE_REQUIREMENT_REVIEW,
        {"user_input_requirement": "用户登录应尽量快速完成"},
    )
    assert "用户登录应尽量快速完成" in text
    assert "ambiguity_list" in text
    assert template_id == row.id
