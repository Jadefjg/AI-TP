from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.api.request_context import get_current_user_optional
from backend.core.config import get_settings
from backend.models.entities import AuditLog


def log_action(
    db: Session,
    *,
    module: str,
    action: str,
    message: str,
    level: str = "info",
    detail: dict | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
    project_id: int | None = None,
) -> AuditLog:
    user = get_current_user_optional()
    row = AuditLog(
        user_id=user_id if user_id is not None else (user.id if user else None),
        organization_id=organization_id if organization_id is not None else (user.organization_id if user else None),
        project_id=project_id,
        module=module[:64],
        action=action[:128],
        level=level[:32],
        message=message[:512],
        detail=detail or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def export_audit_logs_csv(
    db: Session,
    *,
    module: str | None = None,
    organization_id: int | None = None,
    since: datetime | None = None,
    limit: int = 5000,
) -> str:
    query = db.query(AuditLog)
    if module:
        query = query.filter(AuditLog.module == module)
    if organization_id is not None:
        query = query.filter(AuditLog.organization_id == organization_id)
    if since is not None:
        query = query.filter(AuditLog.created_at >= since)
    rows = query.order_by(AuditLog.id.desc()).limit(limit).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "user_id",
            "organization_id",
            "project_id",
            "module",
            "action",
            "level",
            "message",
            "detail",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.user_id or "",
                row.organization_id or "",
                row.project_id or "",
                row.module,
                row.action,
                row.level,
                row.message,
                str(row.detail or ""),
            ]
        )
    return buf.getvalue()


def purge_audit_logs_older_than(db: Session, *, days: int | None = None) -> int:
    settings = get_settings()
    retention = days if days is not None else max(settings.audit_log_retention_days, 1)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
    q = db.query(AuditLog).filter(AuditLog.created_at < cutoff)
    count = q.count()
    q.delete(synchronize_session=False)
    db.commit()
    return count
