"""Transactional, idempotent progression for Agent workflows."""
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from backend.models.entities import AgentWorkflowRun, AgentWorkflowStep, AiAsyncJob, Project
from backend.services.ai_job_queue import enqueue_ai_job
from backend.services.agents.artifact_adapters import build_validated_handoff


def progress_after_step(db: Session, *, project: Project, step_id: int, result: dict[str, Any]) -> AgentWorkflowRun | None:
    """Complete a step and atomically enqueue at most one next step."""
    step = db.query(AgentWorkflowStep).filter_by(id=step_id).with_for_update().one_or_none()
    if not step:
        return None
    run = db.query(AgentWorkflowRun).filter_by(id=step.workflow_id, project_id=project.id).with_for_update().one()
    # New workflows are driven exclusively by LangGraph. This legacy projector
    # remains only for pre-migration runs and must never enqueue a parallel
    # branch for a checkpoint-backed workflow.
    if run.thread_id:
        return run
    if step.status == "completed" and step.detail and step.detail.get("result") == result:
        return run
    # A late/duplicate worker callback must not reopen a terminal workflow.
    if run.status in {"completed", "rejected", "cancelled"} and step.status == "completed":
        return run
    if str(result.get("status", "completed")) in {"failed", "error"}:
        step.status = "failed"
        step.detail = {**(step.detail or {}), "result": result, "error": result.get("error")}
        run.status = "failed"
        run.current_step = step.position
        return run
    step.status = "completed"
    step.detail = {**(step.detail or {}), "result": result}
    if step.agent_key in {"requirement", "perf", "security"} and step.review_status == "not_required":
        step.review_status = "pending_review"
    if step.review_status in {"pending_review", "rejected"}:
        run.status = "pending_review"
        return run
    nxt = db.query(AgentWorkflowStep).filter(
        AgentWorkflowStep.workflow_id == run.id,
        AgentWorkflowStep.position > step.position,
    ).order_by(AgentWorkflowStep.position.asc()).with_for_update().first()
    if not nxt:
        run.status, run.current_step = "completed", step.position
        return run
    run.current_step = nxt.position
    existing = db.query(AiAsyncJob).filter_by(id=nxt.ai_job_id).one_or_none() if nxt.ai_job_id else None
    if not existing or existing.status in {"failed", "cancelled"}:
        nxt.ai_job_id = None
        handoff = build_validated_handoff(nxt.step_name, run_input=dict(run.input_payload or {}), result=result)
        job = enqueue_ai_job(db, project=project, module_type=nxt.step_name,
                             request_payload={**handoff["input"], "workflow_step_id": nxt.id})
        nxt.ai_job_id, nxt.status = job.id, "running"
    run.status = "running"
    return run
