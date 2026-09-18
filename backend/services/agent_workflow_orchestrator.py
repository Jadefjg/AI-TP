"""Database-artifact oriented workflow planning and retry helpers."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from backend.schemas.agent import AgentTrace, AgentWorkflowPlan, WorkflowStep

DEFAULT_PIPELINE = [("requirement", "requirement_review"), ("ui", "ui_automation"),
                    ("interface", "api_automation"), ("perf", "perf_plan"),
                    ("security", "security_scan")]
SIX_AGENT_PIPELINE = [("requirement", "requirement_review"), ("functional_case", "functional_cases"), *DEFAULT_PIPELINE[1:]]


def build_pipeline_plan(project_id: int, *, enabled: set[str] | None = None) -> AgentWorkflowPlan:
    enabled = enabled or {key for key, _ in DEFAULT_PIPELINE}
    return AgentWorkflowPlan(project_id=project_id, steps=[
        WorkflowStep(name=module, agent_key=key) for key, module in DEFAULT_PIPELINE if key in enabled
    ])


def start_step(step: WorkflowStep) -> WorkflowStep:
    step.status, step.attempt = "running", step.attempt + 1
    step.trace.append(AgentTrace(trace_id=str(uuid4()), agent_key=step.agent_key,
                                 step=step.name, status="running",
                                 started_at=datetime.now(timezone.utc).isoformat()))
    return step


def retry_step(step: WorkflowStep) -> bool:
    if step.attempt >= step.max_attempts:
        step.status = "failed"; return False
    step.status = "pending"; return True


def set_review(step: WorkflowStep, status: str) -> WorkflowStep:
    step.review_status = status
    return step
