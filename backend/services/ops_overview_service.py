"""Ops overview aggregation for the operations console."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.version import APP_VERSION
from backend.models.entities import (
    AiAsyncJob,
    AuditLog,
    ExecutionJob,
    JobStatus,
    K6WorkerNode,
    ScheduledJob,
    SystemSetting,
)


def build_ops_overview(db: Session) -> dict[str, Any]:
    settings = get_settings()
    pending_exec = (
        db.query(func.count(ExecutionJob.id)).filter(ExecutionJob.status == JobStatus.pending.value).scalar() or 0
    )
    running_exec = (
        db.query(func.count(ExecutionJob.id)).filter(ExecutionJob.status == JobStatus.running.value).scalar() or 0
    )
    pending_ai = (
        db.query(func.count(AiAsyncJob.id)).filter(AiAsyncJob.status == JobStatus.pending.value).scalar() or 0
    )
    running_ai = (
        db.query(func.count(AiAsyncJob.id)).filter(AiAsyncJob.status == JobStatus.running.value).scalar() or 0
    )
    workers_total = db.query(func.count(K6WorkerNode.id)).scalar() or 0
    workers_enabled = (
        db.query(func.count(K6WorkerNode.id)).filter(K6WorkerNode.enabled.is_(True)).scalar() or 0
    )
    jobs_enabled = (
        db.query(func.count(ScheduledJob.id)).filter(ScheduledJob.enabled.is_(True)).scalar() or 0
    )
    jobs_total = db.query(func.count(ScheduledJob.id)).scalar() or 0
    recent_errors = (
        db.query(AuditLog)
        .filter(AuditLog.level.in_(["error", "warning"]))
        .order_by(AuditLog.id.desc())
        .limit(8)
        .all()
    )

    alert_channels = {
        "run_failure_alert_enabled": bool(settings.run_failure_alert_enabled),
        "channels": (settings.run_failure_alert_channels or "").strip(),
        "generic_webhook_configured": bool((settings.run_failure_webhook_url or "").strip()),
        "dingtalk_configured": bool((settings.dingtalk_webhook_url or "").strip()),
        "wecom_configured": bool((settings.wecom_webhook_url or "").strip()),
        "smtp_dry_run": bool(settings.smtp_dry_run),
        "metrics_auth_enabled": bool(settings.metrics_auth_enabled),
    }

    score = 100
    if pending_exec > 20 or pending_ai > 20:
        score -= 20
    if pending_exec > 50 or pending_ai > 50:
        score -= 20
    if not alert_channels["generic_webhook_configured"] and not alert_channels["dingtalk_configured"]:
        score -= 10
    if jobs_enabled == 0:
        score -= 5
    score = max(0, min(100, score))

    return {
        "api_version": APP_VERSION,
        "health_score": score,
        "queue": {
            "backend": settings.job_queue_backend,
            "execution_pending": int(pending_exec),
            "execution_running": int(running_exec),
            "ai_pending": int(pending_ai),
            "ai_running": int(running_ai),
        },
        "workers": {"total": int(workers_total), "enabled": int(workers_enabled)},
        "scheduled_jobs": {"total": int(jobs_total), "enabled": int(jobs_enabled)},
        "settings_count": int(db.query(func.count(SystemSetting.id)).scalar() or 0),
        "audit_count": int(db.query(func.count(AuditLog.id)).scalar() or 0),
        "alert_channels": alert_channels,
        "recent_alerts": [
            {
                "id": row.id,
                "module": row.module,
                "action": row.action,
                "level": row.level,
                "message": row.message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent_errors
        ],
    }
