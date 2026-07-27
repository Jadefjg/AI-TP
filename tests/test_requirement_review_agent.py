"""Requirement review Agent workflow."""

import asyncio
import json

from backend.core.config import get_settings
from backend.models.entities import Organization, Project
from backend.services.agent_workflow import RequirementReviewWorkflow, _build_agent_requirement_prompt
from backend.services.ai.constants import MODULE_REQUIREMENT_REVIEW
from backend.services.ai.stubs import build_stub_payload
from backend.services.requirement_analyzer import normalize_requirement_review_payload


SAMPLE = "用户发布帖子时系统应尽量快速完成审核，并支持支付打赏与退款。"


def test_build_agent_requirement_prompt_includes_rag():
    prompt = _build_agent_requirement_prompt(SAMPLE, "历史规范：审核需在 24 小时内完成")
    assert "【Agent 分析任务】" in prompt
    assert SAMPLE in prompt
    assert "历史规范" in prompt


def test_build_agent_requirement_prompt_without_rag():
    prompt = _build_agent_requirement_prompt(SAMPLE, "")
    assert "未命中相关知识条目" in prompt


def test_normalize_skips_heuristic_for_online_empty_payload():
    normalized = normalize_requirement_review_payload({"message": "ok"}, SAMPLE, offline_only=False)
    assert all(len(normalized[key]) == 0 for key in normalized)


def test_requirement_review_workflow_persists_review(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "")
    get_settings.cache_clear()
    org = db.query(Organization).first()
    assert org is not None
    project = Project(organization_id=org.id, name="agent-review", code_root=".")
    db.add(project)
    db.commit()
    db.refresh(project)

    workflow = RequirementReviewWorkflow()
    result = asyncio.run(
        workflow.run(db, project, SAMPLE, source_filename="demo.txt", source_format="txt")
    )
    assert result.task.module_type == MODULE_REQUIREMENT_REVIEW
    assert result.task.persisted_ids
    total = sum(len(result.task.payload.get(key) or []) for key in result.task.payload)
    assert total >= 1
    get_settings.cache_clear()


def test_stub_agent_prompt_path():
    prompt = _build_agent_requirement_prompt(SAMPLE, "")
    content = build_stub_payload(
        system_prompt="sys",
        user_prompt=prompt,
        profile="high",
        module_type=MODULE_REQUIREMENT_REVIEW,
        requirement_text=SAMPLE,
    )
    payload = json.loads(content)
    assert sum(len(payload[key]) for key in payload) >= 1
