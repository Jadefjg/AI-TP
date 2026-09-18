from backend.schemas.agent import AgentResult
from backend.services.agent_workflow_orchestrator import (
    build_pipeline_plan, retry_step, set_review, start_step,
)
from backend.services.agents.protocol import normalize_result


def test_pipeline_plan_and_step_lifecycle():
    plan = build_pipeline_plan(7)
    assert [s.agent_key for s in plan.steps] == ["requirement", "ui", "interface", "perf", "security"]
    step = start_step(plan.steps[0])
    assert step.status == "running" and step.attempt == 1 and step.trace
    set_review(step, "pending_review")
    assert step.review_status == "pending_review"
    assert retry_step(step) is True and step.status == "pending"


def test_normalize_legacy_outputs():
    result = normalize_result("interface", {"status": "passed", "job_id": 9, "findings": []})
    assert isinstance(result, AgentResult)
    assert result.agent_key == "interface" and result.artifact_id == 9


def test_failed_agent_result_contract_is_explicit():
    result = normalize_result("interface", {"status": "failed", "error": "timeout"})
    assert result.status == "failed"
    assert result.error == "timeout"
