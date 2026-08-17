"""Async AI generation job queue (RQ / Redis / DB worker)."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db.session import SessionLocal
from backend.models.entities import AiAsyncJob, JobStatus, Project
from backend.services.ai.constants import (
    AI_MODULES,
    MODULE_API_AUTOMATION,
    MODULE_FUNCTIONAL_CASES,
    MODULE_OPENAPI_SPEC,
    MODULE_PERF_PLAN,
    MODULE_REQUIREMENT_REVIEW,
    MODULE_SECURITY_SCAN,
)
from backend.services.audit_service import log_action

logger = logging.getLogger(__name__)

QUEUEABLE_MODULES = frozenset(AI_MODULES)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return f"ai-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _dispatch_ai_queue(job_id: int) -> None:
    settings = get_settings()
    backend = (settings.job_queue_backend or "db").strip().lower()
    if backend == "rq":
        from backend.services.job_queue_rq import enqueue_rq_ai_job

        enqueue_rq_ai_job(job_id)
    elif backend == "celery":
        from backend.services.job_queue_celery import enqueue_celery_ai_job

        enqueue_celery_ai_job(job_id)
    elif backend == "redis" and settings.redis_url:
        from backend.services.job_queue_redis import publish_ai_job

        publish_ai_job(job_id)


def enqueue_ai_job(
    db: Session,
    *,
    project: Project,
    module_type: str,
    request_payload: dict[str, Any],
    max_attempts: int = 2,
) -> AiAsyncJob:
    if module_type not in QUEUEABLE_MODULES:
        raise ValueError(f"unsupported module_type for async AI: {module_type}")
    job = AiAsyncJob(
        project_id=project.id,
        organization_id=project.organization_id,
        module_type=module_type,
        status=JobStatus.pending.value,
        request_payload=request_payload,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    settings = get_settings()
    backend = (settings.job_queue_backend or "db").strip().lower()
    if backend in {"rq", "celery"}:
        _dispatch_ai_queue(job.id)
    elif backend == "redis" and settings.redis_url:
        _dispatch_ai_queue(job.id)
    else:
        # Local/dev: process in a daemon thread so 202 returns immediately without a worker process.
        import threading

        threading.Thread(
            target=_process_ai_job_in_thread,
            args=(job.id,),
            name=f"ai-async-job-{job.id}",
            daemon=True,
        ).start()
    return job


def _process_ai_job_in_thread(job_id: int) -> None:
    session = SessionLocal()
    try:
        process_ai_job(session, job_id, auto_claim=True)
    except Exception:  # noqa: BLE001
        logger.exception("inline ai job thread failed job_id=%s", job_id)
    finally:
        session.close()


def _claim_ai_job(db: Session, job_id: int, worker_id: str) -> AiAsyncJob | None:
    job = db.query(AiAsyncJob).filter(AiAsyncJob.id == job_id).one_or_none()
    if not job or job.cancel_requested:
        return None
    if job.status != JobStatus.pending.value:
        return None
    job.status = JobStatus.running.value
    job.started_at = _now()
    job.attempt_count = int(job.attempt_count or 0) + 1
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("ai job #%s claimed by %s attempt=%s", job.id, worker_id, job.attempt_count)
    return job


def claim_next_pending_ai_job(db: Session, worker_id: str | None = None) -> AiAsyncJob | None:
    wid = worker_id or _worker_id()
    job = (
        db.query(AiAsyncJob)
        .filter(
            AiAsyncJob.status == JobStatus.pending.value,
            AiAsyncJob.cancel_requested.is_(False),
        )
        .order_by(AiAsyncJob.id.asc())
        .first()
    )
    if not job:
        return None
    return _claim_ai_job(db, job.id, wid)


def _task_result_to_dict(result: Any, *, contexts: list[dict] | None = None) -> dict[str, Any]:
    return {
        "module_type": result.module_type,
        "model": result.model,
        "payload": result.payload,
        "prompt_template_id": result.prompt_template_id,
        "persisted_ids": list(result.persisted_ids or []),
        "contexts": contexts if contexts is not None else result.contexts,
        "used_fallback": bool(getattr(result, "used_fallback", False) or "-fallback" in str(result.model)),
    }


def _project_api_context(project: Project) -> str:
    bits = [f"项目: {project.name}"]
    if project.description:
        bits.append(f"描述: {project.description}")
    bits.append(f"仓库来源: {project.repo_source}")
    bits.append(f"code_root: {project.code_root}")
    if project.base_url:
        bits.append(f"base_url: {project.base_url}")
    return "\n".join(bits)


async def _execute_ai_module(db: Session, job: AiAsyncJob, project: Project) -> dict[str, Any]:
    from backend.services.ai.scheduler import run_ai_module
    from backend.services.agent_workflow import RequirementReviewWorkflow

    req = job.request_payload if isinstance(job.request_payload, dict) else {}
    module = job.module_type

    if module == MODULE_REQUIREMENT_REVIEW:
        text = (req.get("requirement_text") or "").strip()
        if not text:
            raise ValueError("requirement_text is required")
        workflow = RequirementReviewWorkflow()
        workflow_result = await workflow.run(
            db,
            project=project,
            requirement_text=text,
            source_filename=req.get("source_filename"),
            source_format=req.get("source_format"),
        )
        log_action(
            db,
            module="ai",
            action="requirement_review.async",
            message=f"async agent review for project #{project.id}",
            detail={
                "job_id": job.id,
                "mode": workflow_result.mode,
                "contexts": len(workflow_result.contexts),
                "review_id": (
                    workflow_result.task.persisted_ids[0] if workflow_result.task.persisted_ids else None
                ),
            },
            organization_id=project.organization_id,
            project_id=project.id,
        )
        return _task_result_to_dict(workflow_result.task, contexts=workflow_result.contexts)

    if module == MODULE_FUNCTIONAL_CASES:
        result = await run_ai_module(
            db,
            project=project,
            module_type=module,
            variables={
                "req_content": req.get("requirement_text") or "",
                "openapi_content": req.get("openapi_content") or "（未提供 OpenAPI 文档）",
            },
            use_rag=True,
        )
        return _task_result_to_dict(result)

    if module == MODULE_API_AUTOMATION:
        project_ctx = _project_api_context(project)
        api_info = (req.get("api_info") or "").strip() or "（未额外提供接口说明）"
        if project_ctx not in api_info:
            api_info = f"{project_ctx}\n\n{api_info}"
        case_info = (req.get("case_info") or "").strip() or (
            "基于当前项目整体能力，覆盖主流程与异常断言，生成接口自动化场景。"
        )
        variables: dict[str, str] = {"case_info": case_info, "api_info": api_info}
        if req.get("case_id") is not None:
            variables["case_id"] = str(req["case_id"])
        result = await run_ai_module(
            db,
            project=project,
            module_type=module,
            variables=variables,
            use_rag=True,
        )
        return _task_result_to_dict(result)

    if module == MODULE_PERF_PLAN:
        result = await run_ai_module(
            db,
            project=project,
            module_type=module,
            variables={
                "biz_desc": req.get("biz_desc") or "",
                "api_doc": req.get("api_doc") or "",
            },
            use_rag=True,
        )
        return _task_result_to_dict(result)

    if module == MODULE_SECURITY_SCAN:
        project_ctx = _project_api_context(project)
        api_params = (req.get("api_params") or "").strip() or (
            f"基于项目「{project.name}」推断主要 HTTP 入参与攻击面，覆盖注入、越权、敏感信息等风险。"
        )
        if project_ctx not in api_params:
            api_params = f"{project_ctx}\n\n{api_params}"
        result = await run_ai_module(
            db,
            project=project,
            module_type=module,
            variables={"api_params": api_params},
            use_rag=True,
        )
        return _task_result_to_dict(result)

    if module == MODULE_OPENAPI_SPEC:
        # Keep discovery/url/manual on the sync HTTP route; async path is AI rewrite only.
        notes = (req.get("notes") or "").strip()
        project_context = _project_api_context(project)
        if notes:
            project_context = f"{project_context}\n\n用户补充: {notes}"
        result = await run_ai_module(
            db,
            project=project,
            module_type=module,
            variables={
                "project_context": project_context,
                "code_signals": req.get("code_signals") or "（异步任务未附带代码信号，请基于项目上下文生成）",
            },
            use_rag=True,
        )
        return _task_result_to_dict(result)

    raise ValueError(f"unsupported module_type: {module}")


def process_ai_job(db: Session, job_id: int, *, auto_claim: bool = True) -> None:
    job = db.query(AiAsyncJob).filter(AiAsyncJob.id == job_id).one_or_none()
    if not job or job.cancel_requested:
        if job and job.cancel_requested:
            job.status = JobStatus.cancelled.value
            job.completed_at = _now()
            db.commit()
        return
    if job.status == JobStatus.pending.value and auto_claim:
        job = _claim_ai_job(db, job_id, _worker_id())
        if not job:
            return
    if job.status != JobStatus.running.value:
        return

    project = (
        db.query(Project)
        .options(selectinload(Project.ai_credential))
        .filter(Project.id == job.project_id)
        .one_or_none()
    )
    if not project:
        job.status = JobStatus.failed.value
        job.last_error = "project not found"
        job.completed_at = _now()
        db.commit()
        return

    try:
        result_payload = asyncio.run(_execute_ai_module(db, job, project))
        job = db.query(AiAsyncJob).filter(AiAsyncJob.id == job_id).one()
        if job.cancel_requested:
            job.status = JobStatus.cancelled.value
        else:
            job.result_payload = result_payload
            job.status = JobStatus.completed.value
        job.completed_at = _now()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(AiAsyncJob).filter(AiAsyncJob.id == job_id).one()
        job.last_error = str(exc)
        if job.attempt_count < job.max_attempts and not job.cancel_requested:
            job.status = JobStatus.pending.value
            job.started_at = None
            job.completed_at = None
            db.commit()
            _dispatch_ai_queue(job.id)
            logger.warning(
                "ai job #%s will retry (%s/%s): %s",
                job.id,
                job.attempt_count,
                job.max_attempts,
                exc,
            )
        else:
            job.status = JobStatus.failed.value
            job.completed_at = _now()
            db.commit()
            logger.exception("ai job #%s failed", job_id)


def process_next_pending_ai_job(worker_id: str | None = None) -> bool:
    wid = worker_id or _worker_id()
    db = SessionLocal()
    try:
        settings = get_settings()
        backend = (settings.job_queue_backend or "db").strip().lower()
        if backend in {"rq", "celery"}:
            return False
        job = claim_next_pending_ai_job(db, wid)
        if not job:
            return False
        process_ai_job(db, job.id, auto_claim=False)
        return True
    finally:
        db.close()
