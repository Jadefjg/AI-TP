from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import AiCallLog, Organization, Project, User


def is_platform_admin(user: User) -> bool:
    return any(role.name == "admin" for role in user.roles)


def is_platform_user(user: User) -> bool:
    """Platform scope: unbound users or bootstrap admin role (even if bound to a default org)."""
    return user.organization_id is None or is_platform_admin(user)


def seed_default_organization(db: Session) -> Organization:
    settings = get_settings()
    slug = (settings.default_organization_slug or "default").strip()
    org = db.query(Organization).filter(Organization.slug == slug).one_or_none()
    if not org:
        org = Organization(
            slug=slug,
            name="默认租户",
            description="单租户升级后的默认组织",
            max_projects=500,
            monthly_ai_token_quota=2_000_000,
        )
        db.add(org)
        db.flush()
    if _has_column(db, "projects", "organization_id"):
        db.query(Project).filter(Project.organization_id.is_(None)).update(
            {Project.organization_id: org.id},
            synchronize_session=False,
        )
    db.commit()
    db.refresh(org)
    return org


def _has_column(db: Session, table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = db.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def get_organization(db: Session, org_id: int) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail="organization is inactive")
    return org


def resolve_organization_id_for_user(user: User, requested_org_id: int | None = None) -> int | None:
    if is_platform_user(user):
        return requested_org_id
    return user.organization_id


def resolve_dashboard_organization_scope(user: User, requested_org_id: int | None = None) -> int | None:
    """Dashboard scope: tenant users always their org; platform admin may pass org id or None (all)."""
    if is_platform_user(user):
        return requested_org_id
    if user.organization_id is None:
        raise HTTPException(status_code=403, detail="organization context required for dashboard")
    if requested_org_id is not None and requested_org_id != user.organization_id:
        raise HTTPException(status_code=403, detail="organization access denied")
    return user.organization_id


def assert_can_access_organization(user: User, org: Organization) -> None:
    if is_platform_user(user):
        return
    if user.organization_id != org.id:
        raise HTTPException(status_code=403, detail="organization access denied")


def filter_projects_for_user(query, user: User):
    if is_platform_user(user):
        return query
    if user.organization_id is None:
        return query.filter(False)
    return query.filter(Project.organization_id == user.organization_id)


def get_project_for_user(db: Session, user: User, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not is_platform_user(user) and project.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="project access denied")
    return project


def assert_project_quota(db: Session, org: Organization) -> None:
    if org.max_projects <= 0:
        return
    count = db.query(func.count(Project.id)).filter(Project.organization_id == org.id).scalar() or 0
    if count >= org.max_projects:
        raise HTTPException(
            status_code=429,
            detail=f"organization project quota exceeded ({count}/{org.max_projects})",
        )


def month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def organization_token_usage(db: Session, org_id: int) -> int:
    since = month_start_utc()
    prompt = (
        db.query(func.coalesce(func.sum(AiCallLog.prompt_tokens), 0))
        .filter(AiCallLog.organization_id == org_id, AiCallLog.created_at >= since)
        .scalar()
        or 0
    )
    completion = (
        db.query(func.coalesce(func.sum(AiCallLog.completion_tokens), 0))
        .filter(AiCallLog.organization_id == org_id, AiCallLog.created_at >= since)
        .scalar()
        or 0
    )
    return int(prompt) + int(completion)


def assert_ai_token_quota(db: Session, org: Organization, *, extra_tokens: int = 0) -> None:
    quota = org.monthly_ai_token_quota
    if quota <= 0:
        return
    used = organization_token_usage(db, org.id)
    if used + extra_tokens > quota:
        raise HTTPException(
            status_code=429,
            detail=f"monthly AI token quota exceeded ({used + extra_tokens}/{quota})",
        )
