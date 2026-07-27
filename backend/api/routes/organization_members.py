from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_user, require_permission
from backend.db.session import get_db
from backend.models.entities import OrganizationMember, User
from backend.schemas.dto import (
    OrganizationMemberByRoleIn,
    OrganizationMemberIn,
    OrganizationMemberOut,
)
from backend.services.audit_service import log_action
from backend.services.member_service import (
    assert_can_manage_org_members,
    bind_member_to_organization,
    list_org_members,
    remove_org_member,
    resolve_roles_by_names,
)
from backend.services.tenant_service import assert_can_access_organization, get_organization

router = APIRouter(prefix="/organizations", tags=["organization-members"])


@router.get(
    "/{org_id}/members",
    response_model=list[OrganizationMemberOut],
    dependencies=[Depends(require_permission("org.member.read"))],
)
def list_members(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationMemberOut]:
    org = get_organization(db, org_id)
    assert_can_access_organization(user, org)
    return [OrganizationMemberOut(**row) for row in list_org_members(db, org_id)]


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberOut,
    dependencies=[Depends(require_permission("org.member.manage"))],
)
def add_member(
    org_id: int,
    body: OrganizationMemberIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMemberOut:
    org = get_organization(db, org_id)
    assert_can_manage_org_members(user, org)
    target = db.query(User).filter(User.id == body.user_id).one_or_none()
    if not target:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="user not found")
    member = bind_member_to_organization(db, org=org, user=target, role_ids=body.role_ids)
    log_action(
        db,
        module="organizations",
        action="org.member.added",
        message=f"user #{target.id} added to org {org.slug}",
        organization_id=org.id,
        detail={"user_id": target.id, "role_ids": body.role_ids},
    )
    rows = list_org_members(db, org_id)
    row = next((r for r in rows if r["user_id"] == target.id), None)
    return OrganizationMemberOut(**row) if row else OrganizationMemberOut(
        id=member.id,
        organization_id=org.id,
        user_id=target.id,
        username=target.username,
        display_name=target.display_name,
        email=target.email,
        is_active=target.is_active,
        role_names=[r.name for r in target.roles],
        created_at=member.created_at,
    )


@router.post(
    "/{org_id}/members/by-role-names",
    response_model=OrganizationMemberOut,
    dependencies=[Depends(require_permission("org.member.manage"))],
)
def add_member_by_role_names(
    org_id: int,
    body: OrganizationMemberByRoleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMemberOut:
    org = get_organization(db, org_id)
    assert_can_manage_org_members(user, org)
    target = db.query(User).filter(User.id == body.user_id).one_or_none()
    if not target:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="user not found")
    roles = resolve_roles_by_names(db, body.role_names)
    member = bind_member_to_organization(db, org=org, user=target, role_ids=[r.id for r in roles])
    log_action(
        db,
        module="organizations",
        action="org.member.roles_bound",
        message=f"user #{target.id} roles bound in org {org.slug}",
        organization_id=org.id,
        detail={"role_names": body.role_names},
    )
    target = (
        db.query(User)
        .options(selectinload(User.roles))
        .filter(User.id == target.id)
        .one()
    )
    return OrganizationMemberOut(
        id=member.id,
        organization_id=org.id,
        user_id=target.id,
        username=target.username,
        display_name=target.display_name,
        email=target.email,
        is_active=target.is_active,
        role_names=[r.name for r in target.roles],
        created_at=member.created_at,
    )


@router.delete(
    "/{org_id}/members/{user_id}",
    response_model=dict,
    dependencies=[Depends(require_permission("org.member.manage"))],
)
def delete_member(
    org_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    org = get_organization(db, org_id)
    assert_can_manage_org_members(user, org)
    remove_org_member(db, org=org, user_id=user_id)
    log_action(
        db,
        module="organizations",
        action="org.member.removed",
        message=f"user #{user_id} removed from org {org.slug}",
        organization_id=org.id,
    )
    return {"ok": True}
