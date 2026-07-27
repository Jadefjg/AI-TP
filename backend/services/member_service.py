from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session, selectinload

from backend.models.entities import Organization, OrganizationMember, Role, User, organization_member_roles
from backend.services.auth_service import user_has_permission
from backend.services.tenant_service import assert_can_access_organization, get_organization, is_platform_user


def assert_can_manage_org_members(user: User, org: Organization) -> None:
    if is_platform_user(user) and user_has_permission(user, "org.member.manage"):
        return
    if is_platform_user(user) and user_has_permission(user, "org.manage"):
        return
    if user.organization_id == org.id and user_has_permission(user, "org.member.manage"):
        return
    raise HTTPException(status_code=403, detail="organization member management denied")


def list_org_members(db: Session, org_id: int) -> list[dict]:
    rows = (
        db.query(OrganizationMember)
        .options(selectinload(OrganizationMember.user).selectinload(User.roles))
        .filter(OrganizationMember.organization_id == org_id)
        .order_by(OrganizationMember.id.asc())
        .all()
    )
    out: list[dict] = []
    for row in rows:
        u = row.user
        out.append(
            {
                "id": row.id,
                "organization_id": org_id,
                "user_id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "email": u.email,
                "is_active": u.is_active,
                "role_names": [r.name for r in u.roles],
                "created_at": row.created_at,
            }
        )
    return out


def bind_member_to_organization(
    db: Session,
    *,
    org: Organization,
    user: User,
    role_ids: list[int],
) -> OrganizationMember:
    if not role_ids:
        raise HTTPException(status_code=400, detail="role_ids required")
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    if len(roles) != len(set(role_ids)):
        raise HTTPException(status_code=400, detail="invalid role_ids")

    user.organization_id = org.id
    user.roles = roles

    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id)
        .one_or_none()
    )
    if not member:
        member = OrganizationMember(organization_id=org.id, user_id=user.id)
        db.add(member)
        db.flush()

    db.execute(
        delete(organization_member_roles).where(
            organization_member_roles.c.organization_id == org.id,
            organization_member_roles.c.user_id == user.id,
        )
    )
    for role in roles:
        db.execute(
            insert(organization_member_roles).values(
                organization_id=org.id,
                user_id=user.id,
                role_id=role.id,
            )
        )
    db.commit()
    db.refresh(member)
    return member


def detach_user_from_organization(db: Session, *, user: User) -> None:
    org_id = user.organization_id
    if org_id is None:
        return
    db.execute(
        delete(organization_member_roles).where(
            organization_member_roles.c.organization_id == org_id,
            organization_member_roles.c.user_id == user.id,
        )
    )
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user.id)
        .one_or_none()
    )
    if member:
        db.delete(member)
    user.organization_id = None


def ensure_org_member(db: Session, *, org_id: int, user_id: int) -> OrganizationMember:
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id)
        .one_or_none()
    )
    if not member:
        member = OrganizationMember(organization_id=org_id, user_id=user_id)
        db.add(member)
        db.flush()
    return member


def _set_user_roles(db: Session, user: User, role_ids: list[int]) -> None:
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all() if role_ids else []
    if role_ids and len(roles) != len(set(role_ids)):
        raise HTTPException(status_code=400, detail="invalid role_ids")
    user.roles = roles
    if user.organization_id:
        db.execute(
            delete(organization_member_roles).where(
                organization_member_roles.c.organization_id == user.organization_id,
                organization_member_roles.c.user_id == user.id,
            )
        )
        for role in roles:
            db.execute(
                insert(organization_member_roles).values(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    role_id=role.id,
                )
            )


def apply_user_admin_update(db: Session, user: User, patch: dict) -> User:
    if "is_active" in patch:
        user.is_active = bool(patch["is_active"])

    roles_changed = "role_ids" in patch
    org_changed = "organization_id" in patch

    if org_changed:
        new_org_id = patch["organization_id"]
        if new_org_id != user.organization_id:
            if user.organization_id is not None:
                detach_user_from_organization(db, user=user)
            if new_org_id is not None:
                org = get_organization(db, new_org_id)
                role_ids = patch["role_ids"] if roles_changed else [r.id for r in user.roles]
                if role_ids:
                    bind_member_to_organization(db, org=org, user=user, role_ids=role_ids)
                    db.refresh(user)
                    return user
                user.organization_id = new_org_id
                ensure_org_member(db, org_id=new_org_id, user_id=user.id)

    if roles_changed:
        _set_user_roles(db, user, patch["role_ids"] or [])

    db.commit()
    db.refresh(user)
    return user


def remove_org_member(db: Session, *, org: Organization, user_id: int) -> None:
    member = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user_id)
        .one_or_none()
    )
    if not member:
        raise HTTPException(status_code=404, detail="organization member not found")
    user = db.query(User).filter(User.id == user_id).one_or_none()
    db.execute(
        delete(organization_member_roles).where(
            organization_member_roles.c.organization_id == org.id,
            organization_member_roles.c.user_id == user_id,
        )
    )
    db.delete(member)
    if user and user.organization_id == org.id:
        user.organization_id = None
        user.roles = []
    db.commit()


def resolve_roles_by_names(db: Session, role_names: list[str]) -> list[Role]:
    names = [n.strip() for n in role_names if n.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="role_names required")
    roles = db.query(Role).filter(Role.name.in_(names)).all()
    missing = set(names) - {r.name for r in roles}
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown roles: {sorted(missing)}")
    return roles


def attach_oidc_user_to_organization(
    db: Session,
    *,
    user: User,
    org_slug: str | None,
) -> Organization:
    from backend.core.config import get_settings
    from backend.services.tenant_service import seed_default_organization

    settings = get_settings()
    slug = (org_slug or settings.oidc_default_organization_slug or "default").strip().lower()
    org = db.query(Organization).filter(Organization.slug == slug).one_or_none()
    if not org and settings.oidc_auto_create_organization:
        org = Organization(slug=slug, name=slug, description="OIDC auto-provisioned")
        db.add(org)
        db.commit()
        db.refresh(org)
    if not org:
        org = seed_default_organization(db)
    role_names = [n.strip() for n in (settings.oidc_default_member_roles or "member").split(",") if n.strip()]
    roles = resolve_roles_by_names(db, role_names)
    bind_member_to_organization(db, org=org, user=user, role_ids=[r.id for r in roles])
    return org
