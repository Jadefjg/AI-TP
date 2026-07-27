from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_any_permission, require_permission
from backend.db.session import get_db
from backend.models.entities import Organization, Project, User
from backend.schemas.dto import (
    OrganizationCreate,
    OrganizationOut,
    OrganizationQuotaOut,
    OrganizationUpdate,
)
from backend.services.audit_service import log_action
from backend.services.tenant_service import (
    assert_can_access_organization,
    get_organization,
    is_platform_user,
    organization_token_usage,
    resolve_organization_id_for_user,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get(
    "",
    response_model=list[OrganizationOut],
    dependencies=[Depends(require_any_permission("org.read", "org.manage"))],
)
def list_organizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Organization]:
    query = db.query(Organization).order_by(Organization.id.asc())
    if not is_platform_user(user):
        query = query.filter(Organization.id == user.organization_id)
    return query.all()


@router.post("", response_model=OrganizationOut, dependencies=[Depends(require_permission("org.manage"))])
def create_organization(body: OrganizationCreate, db: Session = Depends(get_db)) -> Organization:
    slug = body.slug.strip().lower()
    if db.query(Organization).filter(Organization.slug == slug).one_or_none():
        raise HTTPException(status_code=409, detail="部门编码已存在，请更换编码")
    row = Organization(
        slug=slug,
        name=body.name,
        description=body.description,
        max_projects=body.max_projects,
        monthly_ai_token_quota=body.monthly_ai_token_quota,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, module="organizations", action="org.created", message=f"org {row.slug} created", detail={"id": row.id})
    return row


@router.get("/{org_id}", response_model=OrganizationOut, dependencies=[Depends(require_permission("org.read"))])
def get_org(org_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Organization:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    return org


@router.patch("/{org_id}", response_model=OrganizationOut, dependencies=[Depends(require_permission("org.manage"))])
def update_org(org_id: int, body: OrganizationUpdate, db: Session = Depends(get_db)) -> Organization:
    org = get_organization(db, org_id)
    if body.name is not None:
        org.name = body.name
    if body.description is not None:
        org.description = body.description
    if body.max_projects is not None:
        org.max_projects = body.max_projects
    if body.monthly_ai_token_quota is not None:
        org.monthly_ai_token_quota = body.monthly_ai_token_quota
    if body.is_active is not None:
        org.is_active = body.is_active
    db.commit()
    db.refresh(org)
    log_action(db, module="organizations", action="org.updated", message=f"org {org.slug} updated", organization_id=org.id)
    return org


@router.get("/{org_id}/quota", response_model=OrganizationQuotaOut, dependencies=[Depends(require_permission("org.read"))])
def org_quota(org_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrganizationQuotaOut:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    project_count = db.query(func.count(Project.id)).filter(Project.organization_id == org.id).scalar() or 0
    tokens_used = organization_token_usage(db, org.id)
    return OrganizationQuotaOut(
        organization_id=org.id,
        slug=org.slug,
        project_count=int(project_count),
        max_projects=org.max_projects,
        monthly_ai_token_quota=org.monthly_ai_token_quota,
        monthly_tokens_used=tokens_used,
        monthly_tokens_remaining=(
            None if org.monthly_ai_token_quota <= 0 else max(org.monthly_ai_token_quota - tokens_used, 0)
        ),
    )
