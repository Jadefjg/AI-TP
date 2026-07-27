from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_permission
from backend.db.session import get_db
from backend.models.entities import User
from backend.services.ai_usage_service import build_ai_usage_summary
from backend.services.auth_service import user_has_permission
from backend.services.dashboard_service import DashboardScope, build_dashboard_summary, build_run_trends
from backend.services.system_service import build_system_overview
from backend.services.tenant_service import resolve_dashboard_organization_scope
from backend.schemas.dto import DashboardOverviewOut, DashboardRunTrendsOut, DashboardSummaryOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/overview",
    response_model=DashboardOverviewOut,
    dependencies=[Depends(require_permission("dashboard.read"))],
)
def get_dashboard_overview(
    days: int = Query(default=7, ge=1, le=90),
    organization_id: int | None = Query(default=None, description="平台管理员可选；租户用户忽略"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOverviewOut:
    org_scope = resolve_dashboard_organization_scope(user, organization_id)
    scope = DashboardScope(organization_id=org_scope)
    return DashboardOverviewOut(
        summary=build_dashboard_summary(db, scope=scope),
        run_trends=build_run_trends(db, scope=scope, days=days),
        system_overview=build_system_overview(db) if user_has_permission(user, "system.read") else None,
        ai_usage=build_ai_usage_summary(db, organization_id=org_scope)
        if user_has_permission(user, "ai.read")
        else None,
    )


@router.get("/summary", response_model=DashboardSummaryOut, dependencies=[Depends(require_permission("dashboard.read"))])
def get_dashboard_summary(
    organization_id: int | None = Query(default=None, description="平台管理员可选；租户用户忽略"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardSummaryOut:
    org_scope = resolve_dashboard_organization_scope(user, organization_id)
    return build_dashboard_summary(db, scope=DashboardScope(organization_id=org_scope))


@router.get(
    "/run-trends",
    response_model=DashboardRunTrendsOut,
    dependencies=[Depends(require_permission("dashboard.read"))],
)
def get_run_trends(
    days: int = Query(default=7, ge=1, le=90),
    organization_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardRunTrendsOut:
    org_scope = resolve_dashboard_organization_scope(user, organization_id)
    return build_run_trends(db, scope=DashboardScope(organization_id=org_scope), days=days)
