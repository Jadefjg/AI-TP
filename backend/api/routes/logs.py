from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_permission
from backend.db.session import get_db
from backend.models.entities import AuditLog, User
from backend.schemas.dto import AuditLogOut, AuditRetentionOut
from backend.services.audit_service import export_audit_logs_csv, log_action, purge_audit_logs_older_than
from backend.services.tenant_service import is_platform_user, resolve_organization_id_for_user

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[AuditLogOut], dependencies=[Depends(require_permission("logs.read"))])
def list_logs(
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    level: str | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    query = db.query(AuditLog)
    if module:
        query = query.filter(AuditLog.module == module)
    if action:
        query = query.filter(AuditLog.action.contains(action))
    if level:
        query = query.filter(AuditLog.level == level)
    scoped_org = resolve_organization_id_for_user(user, organization_id)
    if not is_platform_user(user):
        query = query.filter(AuditLog.organization_id == scoped_org)
    elif organization_id is not None:
        query = query.filter(AuditLog.organization_id == organization_id)
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    return query.order_by(AuditLog.id.desc()).limit(limit).all()


@router.get(
    "/export",
    response_class=PlainTextResponse,
    dependencies=[Depends(require_permission("audit.export"))],
)
def export_logs(
    module: str | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    scoped_org = resolve_organization_id_for_user(user, organization_id)
    if not is_platform_user(user):
        scoped_org = user.organization_id
    since = datetime.now(timezone.utc) - timedelta(days=days)
    csv_text = export_audit_logs_csv(
        db,
        module=module,
        organization_id=scoped_org,
        since=since,
    )
    log_action(
        db,
        module="audit",
        action="audit.export",
        message="audit logs exported",
        organization_id=scoped_org,
        detail={"module": module, "days": days},
    )
    return PlainTextResponse(csv_text, media_type="text/csv")


@router.post(
    "/retention/purge",
    response_model=AuditRetentionOut,
    dependencies=[Depends(require_permission("audit.manage"))],
)
def purge_logs(
    days: int | None = Query(default=None, ge=1, le=3650),
    db: Session = Depends(get_db),
) -> AuditRetentionOut:
    deleted = purge_audit_logs_older_than(db, days=days)
    log_action(
        db,
        module="audit",
        action="audit.purge",
        message=f"purged {deleted} audit logs",
        detail={"days": days},
    )
    return AuditRetentionOut(deleted=deleted)
