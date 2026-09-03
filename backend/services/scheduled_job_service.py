"""Whitelist-only scheduled ops jobs (no shell/SQL injection surface)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.db.session import SessionLocal
from backend.models.entities import ScheduledJob, ScheduledJobRun
from backend.services.audit_service import log_action, purge_audit_logs_older_than

logger = logging.getLogger(__name__)

HandlerFn = Callable[[Session, dict[str, Any] | None], dict[str, Any]]

_SCHEDULER_STARTED = False
_SCHEDULER_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _handler_audit_purge(db: Session, params: dict[str, Any] | None) -> dict[str, Any]:
    days = int((params or {}).get("days") or 180)
    deleted = purge_audit_logs_older_than(db, days=days)
    return {"deleted": deleted, "days": days}


def _handler_recover_stale_jobs(db: Session, params: dict[str, Any] | None) -> dict[str, Any]:
    from backend.services.job_queue import recover_stale_execution_jobs

    recovered = recover_stale_execution_jobs()
    return {"recovered": recovered}


def _handler_health_snapshot(db: Session, params: dict[str, Any] | None) -> dict[str, Any]:
    from sqlalchemy import func

    from backend.models.entities import AiAsyncJob, ExecutionJob, JobStatus

    pending_exec = (
        db.query(func.count(ExecutionJob.id)).filter(ExecutionJob.status == JobStatus.pending.value).scalar() or 0
    )
    pending_ai = (
        db.query(func.count(AiAsyncJob.id)).filter(AiAsyncJob.status == JobStatus.pending.value).scalar() or 0
    )
    snapshot = {"execution_pending": int(pending_exec), "ai_pending": int(pending_ai), "ok": True}
    log_action(
        db,
        module="ops",
        action="ops.health_snapshot",
        message="scheduled health snapshot",
        detail=snapshot,
        level="info",
    )
    return snapshot


JOB_HANDLERS: dict[str, HandlerFn] = {
    "audit.purge_retention": _handler_audit_purge,
    "jobs.recover_stale": _handler_recover_stale_jobs,
    "ops.health_snapshot": _handler_health_snapshot,
}


def list_handler_catalog() -> list[dict[str, str]]:
    return [
        {"key": "audit.purge_retention", "label": "审计日志留存清理", "description": "按天数清理过期审计日志"},
        {"key": "jobs.recover_stale", "label": "恢复僵尸执行任务", "description": "回收超时未完成的 execution_jobs"},
        {"key": "ops.health_snapshot", "label": "运维健康快照", "description": "记录队列积压并写入审计"},
    ]


def seed_default_scheduled_jobs(db: Session) -> None:
    defaults = [
        ("audit-purge-180d", "audit.purge_retention", "清理 180 天前审计日志", 86400, {"days": 180}),
        ("recover-stale-jobs", "jobs.recover_stale", "每小时回收僵尸任务", 3600, {}),
        ("ops-health-snapshot", "ops.health_snapshot", "每 15 分钟健康快照", 900, {}),
    ]
    for name, handler, desc, interval, params in defaults:
        row = db.query(ScheduledJob).filter(ScheduledJob.name == name).one_or_none()
        if row:
            continue
        now = _now()
        db.add(
            ScheduledJob(
                name=name,
                handler_key=handler,
                description=desc,
                interval_seconds=interval,
                enabled=True,
                params=params,
                next_run_at=now + timedelta(seconds=interval),
            )
        )
    db.commit()


def list_jobs(db: Session) -> list[ScheduledJob]:
    return db.query(ScheduledJob).order_by(ScheduledJob.id.asc()).all()


def list_job_runs(db: Session, job_id: int, *, limit: int = 50) -> list[ScheduledJobRun]:
    return (
        db.query(ScheduledJobRun)
        .filter(ScheduledJobRun.job_id == job_id)
        .order_by(ScheduledJobRun.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


def upsert_job(
    db: Session,
    *,
    name: str,
    handler_key: str,
    description: str | None,
    interval_seconds: int,
    enabled: bool,
    params: dict[str, Any] | None,
) -> ScheduledJob:
    if handler_key not in JOB_HANDLERS:
        raise ValueError(f"unsupported handler_key: {handler_key}")
    interval_seconds = max(60, min(int(interval_seconds), 86400 * 30))
    row = db.query(ScheduledJob).filter(ScheduledJob.name == name).one_or_none()
    now = _now()
    if row:
        row.handler_key = handler_key
        row.description = description
        row.interval_seconds = interval_seconds
        row.enabled = enabled
        row.params = params
        if enabled and (row.next_run_at is None or not row.enabled):
            row.next_run_at = now + timedelta(seconds=interval_seconds)
    else:
        row = ScheduledJob(
            name=name,
            handler_key=handler_key,
            description=description,
            interval_seconds=interval_seconds,
            enabled=enabled,
            params=params,
            next_run_at=now + timedelta(seconds=interval_seconds) if enabled else None,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_job_enabled(db: Session, job_id: int, enabled: bool) -> ScheduledJob:
    row = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).one_or_none()
    if not row:
        raise ValueError("job not found")
    row.enabled = enabled
    if enabled:
        row.next_run_at = _now() + timedelta(seconds=max(60, row.interval_seconds))
    db.commit()
    db.refresh(row)
    return row


def run_job(db: Session, job_id: int, *, trigger: str = "manual") -> ScheduledJobRun:
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).one_or_none()
    if not job:
        raise ValueError("job not found")
    handler = JOB_HANDLERS.get(job.handler_key)
    if not handler:
        raise ValueError(f"unsupported handler_key: {job.handler_key}")

    # Simple single-flight: skip if a run is already running for this job.
    busy = (
        db.query(ScheduledJobRun)
        .filter(ScheduledJobRun.job_id == job.id, ScheduledJobRun.status == "running")
        .first()
    )
    if busy:
        raise ValueError("job already running")

    started = _now()
    run = ScheduledJobRun(job_id=job.id, status="running", started_at=started, trigger=trigger)
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = handler(db, job.params if isinstance(job.params, dict) else None)
        finished = _now()
        run.status = "completed"
        run.finished_at = finished
        run.duration_ms = int((finished - started).total_seconds() * 1000)
        run.result = result
        job.last_run_at = finished
        job.last_status = "completed"
        job.last_error = None
        job.next_run_at = finished + timedelta(seconds=max(60, job.interval_seconds))
        db.add(run)
        db.add(job)
        db.commit()
        db.refresh(run)
        log_action(
            db,
            module="ops",
            action="schedule.run",
            message=f"scheduled job {job.name} completed",
            detail={"job_id": job.id, "run_id": run.id, "trigger": trigger, "result": result},
        )
        return run
    except Exception as exc:  # noqa: BLE001
        finished = _now()
        run.status = "failed"
        run.finished_at = finished
        run.duration_ms = int((finished - started).total_seconds() * 1000)
        run.error = str(exc)
        job.last_run_at = finished
        job.last_status = "failed"
        job.last_error = str(exc)
        job.next_run_at = finished + timedelta(seconds=max(60, job.interval_seconds))
        db.add(run)
        db.add(job)
        db.commit()
        db.refresh(run)
        log_action(
            db,
            module="ops",
            action="schedule.run_failed",
            message=f"scheduled job {job.name} failed",
            level="error",
            detail={"job_id": job.id, "run_id": run.id, "error": str(exc)},
        )
        return run


def tick_due_jobs() -> int:
    session = SessionLocal()
    ran = 0
    try:
        now = _now()
        due = (
            session.query(ScheduledJob)
            .filter(
                ScheduledJob.enabled.is_(True),
                ScheduledJob.next_run_at.isnot(None),
                ScheduledJob.next_run_at <= now,
            )
            .order_by(ScheduledJob.id.asc())
            .all()
        )
        for job in due:
            try:
                run_job(session, job.id, trigger="schedule")
                ran += 1
            except Exception:  # noqa: BLE001
                logger.exception("scheduled job tick failed job_id=%s", job.id)
        return ran
    finally:
        session.close()


def _scheduler_loop() -> None:
    while True:
        try:
            tick_due_jobs()
        except Exception:  # noqa: BLE001
            logger.exception("ops scheduler loop error")
        time.sleep(30)


def start_ops_scheduler() -> None:
    global _SCHEDULER_STARTED
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        thread = threading.Thread(target=_scheduler_loop, name="ops-scheduler", daemon=True)
        thread.start()
        _SCHEDULER_STARTED = True
        logger.info("ops scheduler started")
