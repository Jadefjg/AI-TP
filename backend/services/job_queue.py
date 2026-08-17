from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db.session import SessionLocal
from backend.models.entities import ExecutionJob, ItemStatus, JobStatus, RunStatus, TestRun
from backend.services.audit_service import log_action
from backend.services.job_queue_redis import pop_job, publish_job
from backend.services.run_alert_service import notify_run_failure


def _dispatch_queue(job_id: int) -> None:
    settings = get_settings()
    backend = (settings.job_queue_backend or "db").strip().lower()
    if backend == "rq":
        from backend.services.job_queue_rq import enqueue_rq_job

        enqueue_rq_job(job_id)
    elif backend == "celery":
        from backend.services.job_queue_celery import enqueue_celery_job

        enqueue_celery_job(job_id)
    elif backend == "redis" and settings.redis_url:
        publish_job(job_id)

logger = logging.getLogger(__name__)

JOB_TYPE_TEST_RUN = "test_run"
_worker_started = False
_worker_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def enqueue_test_run_job(
    db: Session,
    *,
    run_id: int,
    command_overrides: dict[str, str] | None,
    run_options: dict | None,
    max_attempts: int = 3,
) -> ExecutionJob:
    existing = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    if existing:
        return existing
    job = ExecutionJob(
        job_type=JOB_TYPE_TEST_RUN,
        run_id=run_id,
        status=JobStatus.pending.value,
        payload={
            "command_overrides": command_overrides,
            "run_options": run_options or {},
        },
        max_attempts=max_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _dispatch_queue(job.id)
    return job


def is_run_cancel_requested(db: Session, run_id: int) -> bool:
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    return bool(job and job.cancel_requested)


def _finalize_interrupted_run(
    db: Session,
    *,
    job: ExecutionJob,
    run: TestRun,
    reason: str,
    cancel: bool = False,
) -> None:
    """Mark orphaned running job/run as terminal so the UI is not stuck forever."""
    now = _now()
    for item in run.items:
        if item.status in {ItemStatus.pending.value, ItemStatus.running.value}:
            was_running = item.status == ItemStatus.running.value
            # Never-started steps → skipped; interrupted mid-step → error.
            item.status = ItemStatus.error.value if was_running else ItemStatus.skipped.value
            item.finished_at = item.finished_at or now
            detail = item.detail if isinstance(item.detail, dict) else {}
            item.detail = {**detail, "reason": reason}
            if was_running:
                item.stderr = ((item.stderr or "") + f"\n[{reason}]").strip()

    run.status = RunStatus.cancelled.value if cancel else RunStatus.failed.value
    run.completed_at = now
    run.error_message = reason
    job.status = JobStatus.cancelled.value if cancel else JobStatus.failed.value
    job.completed_at = now
    job.last_error = reason
    job.cancel_requested = True if cancel else job.cancel_requested
    db.commit()
    log_action(
        db,
        module="jobs",
        action="job.recovered_stale" if not cancel else "job.force_cancelled",
        level="warning",
        message=f"run #{run.id} finalized after interrupt ({run.status})",
        detail={"run_id": run.id, "job_id": job.id, "reason": reason, "run_status": run.status},
    )


def job_is_stale(job: ExecutionJob, *, max_age_sec: int | None = None) -> bool:
    """Age-based stale detection (safe while a live worker may still be executing)."""
    if job.status != JobStatus.running.value:
        return False
    settings = get_settings()
    if not job.started_at:
        return True
    age = max_age_sec
    if age is None:
        age = int(settings.default_test_timeout_sec) + 120
    started = job.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (_now() - started).total_seconds() >= age


def recover_stale_execution_jobs(db: Session | None = None) -> int:
    """Recover jobs left in running after worker/process crash.

    Returns number of recovered jobs.
    """
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    recovered = 0
    settings = get_settings()
    backend = (settings.job_queue_backend or "db").strip().lower()
    # Embedded API worker: leftover "running" rows after process restart are always orphaned.
    orphan_all_running = bool(settings.job_worker_in_api and backend in {"db", "redis", ""})
    try:
        jobs = (
            db.query(ExecutionJob)
            .filter(ExecutionJob.status == JobStatus.running.value)
            .order_by(ExecutionJob.id.asc())
            .all()
        )
        for job in jobs:
            if not orphan_all_running and not job_is_stale(job):
                continue
            run = (
                db.query(TestRun)
                .options(selectinload(TestRun.items))
                .filter(TestRun.id == job.run_id)
                .one_or_none()
            )
            if not run:
                job.status = JobStatus.failed.value
                job.last_error = "run not found during stale recovery"
                job.completed_at = _now()
                db.commit()
                recovered += 1
                continue
            if run.status not in {RunStatus.running.value, RunStatus.pending.value}:
                job.status = (
                    JobStatus.completed.value
                    if run.status == RunStatus.completed.value
                    else JobStatus.cancelled.value
                    if run.status == RunStatus.cancelled.value
                    else JobStatus.failed.value
                )
                job.completed_at = job.completed_at or _now()
                job.last_error = job.last_error or "aligned with terminal run during recovery"
                db.commit()
                recovered += 1
                continue
            _finalize_interrupted_run(
                db,
                job=job,
                run=run,
                reason="执行进程中断或超时未回收：任务已自动结束（可点「重试」重新执行）",
                cancel=False,
            )
            recovered += 1
        return recovered
    finally:
        if own:
            db.close()


def cancel_run_job(db: Session, run_id: int) -> ExecutionJob:
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    if not job:
        raise ValueError("execution job not found")
    run = (
        db.query(TestRun)
        .options(selectinload(TestRun.items))
        .filter(TestRun.id == run_id)
        .one_or_none()
    )
    if not run:
        raise ValueError("run not found")

    job.cancel_requested = True
    if job.status in {JobStatus.pending.value}:
        job.status = JobStatus.cancelled.value
        job.completed_at = _now()
        run.status = RunStatus.cancelled.value
        run.completed_at = _now()
        db.commit()
    elif job.status == JobStatus.running.value and job_is_stale(job):
        # Worker already dead — force-cancel so UI is not stuck on「执行中」.
        _finalize_interrupted_run(
            db,
            job=job,
            run=run,
            reason="用户取消：检测到任务已中断，已强制结束",
            cancel=True,
        )
    else:
        db.commit()
    db.refresh(job)
    log_action(
        db,
        module="jobs",
        action="job.cancel_requested",
        message=f"cancel requested for run #{run_id}",
        detail={"run_id": run_id, "job_id": job.id, "job_status": job.status},
    )
    return job


def retry_run_job(db: Session, run_id: int) -> ExecutionJob:
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    if not job:
        raise ValueError("execution job not found")
    run = (
        db.query(TestRun)
        .options(selectinload(TestRun.items))
        .filter(TestRun.id == run_id)
        .one_or_none()
    )
    if not run:
        raise ValueError("run not found")

    job.status = JobStatus.pending.value
    job.cancel_requested = False
    job.attempt_count = 0
    job.last_error = None
    job.started_at = None
    job.completed_at = None
    run.status = RunStatus.pending.value
    run.completed_at = None
    run.error_message = None
    for item in run.items:
        item.status = "pending"
        item.command = None
        item.stdout = None
        item.stderr = None
        item.exit_code = None
        item.detail = None
        item.started_at = None
        item.finished_at = None
    db.commit()
    db.refresh(job)
    _dispatch_queue(job.id)
    log_action(
        db,
        module="jobs",
        action="job.retry",
        message=f"job retry queued for run #{run_id}",
        detail={"run_id": run_id, "job_id": job.id},
    )
    return job


def _claim_job(db: Session, job_id: int, worker_id: str) -> ExecutionJob | None:
    job = db.query(ExecutionJob).filter(ExecutionJob.id == job_id).one_or_none()
    if not job or job.status != JobStatus.pending.value or job.cancel_requested:
        return None
    updated = (
        db.query(ExecutionJob)
        .filter(ExecutionJob.id == job_id, ExecutionJob.status == JobStatus.pending.value)
        .update(
            {
                ExecutionJob.status: JobStatus.running.value,
                ExecutionJob.started_at: _now(),
                ExecutionJob.attempt_count: job.attempt_count + 1,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        return None
    run = db.query(TestRun).filter(TestRun.id == job.run_id).one_or_none()
    if run:
        run.status = RunStatus.running.value
    payload = job.payload if isinstance(job.payload, dict) else {}
    payload["worker_id"] = worker_id
    job.payload = payload
    db.commit()
    return db.query(ExecutionJob).filter(ExecutionJob.id == job_id).one_or_none()


def claim_next_pending_job(db: Session, worker_id: str) -> ExecutionJob | None:
    job = (
        db.query(ExecutionJob)
        .filter(
            ExecutionJob.status == JobStatus.pending.value,
            ExecutionJob.cancel_requested.is_(False),
        )
        .order_by(ExecutionJob.id.asc())
        .first()
    )
    if not job:
        return None
    return _claim_job(db, job.id, worker_id)


def process_job(db: Session, job_id: int, *, auto_claim: bool = True) -> None:
    job = db.query(ExecutionJob).filter(ExecutionJob.id == job_id).one_or_none()
    if not job or job.cancel_requested:
        return
    if job.status == JobStatus.pending.value and auto_claim:
        job = _claim_job(db, job_id, _worker_id())
        if not job:
            return
    if job.status != JobStatus.running.value:
        return

    run = (
        db.query(TestRun)
        .options(selectinload(TestRun.items), selectinload(TestRun.project))
        .filter(TestRun.id == job.run_id)
        .one_or_none()
    )
    if not run:
        job.status = JobStatus.failed.value
        job.last_error = "run not found"
        job.completed_at = _now()
        db.commit()
        return

    payload = job.payload if isinstance(job.payload, dict) else {}
    overrides = payload.get("command_overrides")
    run_options = payload.get("run_options")

    try:
        if job.cancel_requested:
            run.status = RunStatus.cancelled.value
            job.status = JobStatus.cancelled.value
        else:
            from backend.services.orchestrator import execute_run

            execute_run(db, run, run.project, overrides, run_options, job_id=job.id)
            if is_run_cancel_requested(db, run.id):
                run.status = RunStatus.cancelled.value
                job.status = JobStatus.cancelled.value
            else:
                job.status = JobStatus.completed.value if run.status != RunStatus.failed.value else JobStatus.failed.value
        job.completed_at = _now()
        db.commit()
        if job.status == JobStatus.failed.value:
            _alert_job_failure(db, job, run)
        _record_job_metric(job.status)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(ExecutionJob).filter(ExecutionJob.id == job_id).one()
        run = db.query(TestRun).filter(TestRun.id == job.run_id).one()
        job.last_error = str(exc)
        run.status = RunStatus.failed.value
        run.error_message = str(exc)
        run.completed_at = _now()
        if job.attempt_count < job.max_attempts and not job.cancel_requested:
            job.status = JobStatus.pending.value
            job.completed_at = None
            job.started_at = None
            settings = get_settings()
            _dispatch_queue(job.id)
            log_action(
                db,
                module="jobs",
                action="job.retry_scheduled",
                level="warning",
                message=f"job #{job.id} will retry ({job.attempt_count}/{job.max_attempts})",
                detail={"run_id": run.id, "error": str(exc)},
            )
        else:
            job.status = JobStatus.failed.value
            job.completed_at = _now()
            _alert_job_failure(db, job, run, error=str(exc))
        _record_job_metric(job.status)
        db.commit()


def _record_job_metric(status: str) -> None:
    try:
        from backend.core.metrics import JOBS_TOTAL

        JOBS_TOTAL.labels(status=status, backend=get_settings().job_queue_backend).inc()
    except Exception:  # noqa: BLE001
        pass


def _alert_job_failure(db: Session, job: ExecutionJob, run: TestRun, error: str | None = None) -> None:
    log_action(
        db,
        module="jobs",
        action="job.failed",
        level="error",
        message=f"execution job failed for run #{run.id} after {job.attempt_count} attempts",
        detail={
            "job_id": job.id,
            "run_id": run.id,
            "project_id": run.project_id,
            "attempts": job.attempt_count,
            "last_error": error or job.last_error,
            "run_status": run.status,
        },
    )
    try:
        notify_run_failure(
            db,
            run=run,
            project=run.project,
            job_id=job.id,
            last_error=error or job.last_error,
            attempts=job.attempt_count,
        )
    except Exception:  # noqa: BLE001
        logger.exception("run failure notification error")


def process_next_pending_job(worker_id: str | None = None) -> bool:
    wid = worker_id or _worker_id()
    db = SessionLocal()
    try:
        settings = get_settings()
        job: ExecutionJob | None = None
        backend = (settings.job_queue_backend or "db").strip().lower()
        if backend == "redis" and settings.redis_url:
            from backend.services.job_queue_redis import pop_ai_job, pop_job

            ai_job_id = pop_ai_job(timeout_sec=0)
            if ai_job_id:
                from backend.services.ai_job_queue import process_ai_job as _process_ai

                _process_ai(db, ai_job_id, auto_claim=True)
                return True
            job_id = pop_job(timeout_sec=1)
            if job_id:
                job = _claim_job(db, job_id, wid)
        if backend in {"rq", "celery"}:
            return False
        if not job:
            job = claim_next_pending_job(db, wid)
        if job:
            process_job(db, job.id)
            return True
        # Alternate: drain pending AI jobs on db backend.
        from backend.services.ai_job_queue import process_next_pending_ai_job

        return process_next_pending_ai_job(wid)
    finally:
        db.close()


def run_worker_forever(*, stop_flag=None, worker_id: str | None = None) -> None:
    wid = worker_id or _worker_id()
    logger.info("execution worker loop started as %s", wid)
    while stop_flag is None or not stop_flag():
        try:
            processed = process_next_pending_job(wid)
            if not processed:
                time.sleep(1.0)
        except Exception:  # noqa: BLE001
            logger.exception("execution job worker error")
            time.sleep(2.0)


def _worker_loop() -> None:
    run_worker_forever()


def start_job_worker() -> None:
    global _worker_started
    settings = get_settings()
    if not settings.job_worker_in_api:
        logger.info("embedded job worker disabled (JOB_WORKER_IN_API=false)")
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, name="execution-job-worker", daemon=True)
        thread.start()
        _worker_started = True
