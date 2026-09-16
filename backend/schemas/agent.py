"""Shared contracts for business Agents."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


AgentStatus = Literal["pending", "running", "completed", "failed", "skipped", "cancelled"]
ReviewStatus = Literal["not_required", "pending_review", "approved", "rejected"]


class AgentTrace(BaseModel):
    trace_id: str
    agent_key: str
    step: str
    status: AgentStatus = "completed"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    agent_key: str
    status: AgentStatus = "completed"
    payload: Any = None
    artifact_id: int | None = None
    review_status: ReviewStatus = "not_required"
    attempt: int = 1
    max_attempts: int = 3
    trace: list[AgentTrace] = Field(default_factory=list)
    error: str | None = None


class WorkflowStep(BaseModel):
    name: str
    agent_key: str
    status: AgentStatus = "pending"
    input_artifact_id: int | None = None
    output_artifact_id: int | None = None
    review_status: ReviewStatus = "not_required"
    attempt: int = 0
    max_attempts: int = 3
    trace: list[AgentTrace] = Field(default_factory=list)


class AgentWorkflowPlan(BaseModel):
    project_id: int
    steps: list[WorkflowStep]
    status: AgentStatus = "pending"
