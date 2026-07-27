from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import require_permission
from backend.db.session import get_db
from backend.models.entities import Permission, Role, User
from backend.schemas.dto import (
    PermissionCreate,
    PermissionOut,
    RoleAssignPermissionsIn,
    RoleCreate,
    RoleOut,
    UserAdminUpdate,
    UserAssignRolesIn,
    UserBatchUpdateIn,
    UserCreate,
    UserOut,
)
from backend.services.audit_service import log_action
from backend.services.auth_service import hash_password
from backend.services.member_service import apply_user_admin_update, bind_member_to_organization, resolve_roles_by_names
from backend.services.tenant_service import get_organization

router = APIRouter(prefix="/admin", tags=["rbac"])


def _load_user_out(db: Session, user_id: int) -> User:
    row = (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.id == user_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    return row


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_permission("user.manage"))])
def create_user(body: UserCreate, db: Session = Depends(get_db)) -> User:
    exists = db.query(User).filter(User.username == body.username).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="username already exists")
    row = User(
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        password_hash=hash_password(body.password),
        is_active=body.is_active,
        organization_id=body.organization_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if body.organization_id and body.role_names:
        org = get_organization(db, body.organization_id)
        roles = resolve_roles_by_names(db, body.role_names)
        bind_member_to_organization(db, org=org, user=row, role_ids=[r.id for r in roles])
    log_action(
        db,
        module="rbac",
        action="user.created",
        message=f"user {row.username} created",
        detail={"user_id": row.id},
    )
    return (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.id == row.id)
        .one()
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_permission("user.manage"))],
)
def update_user(user_id: int, body: UserAdminUpdate, db: Session = Depends(get_db)) -> User:
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="no updates provided")
    apply_user_admin_update(db, user, patch)
    log_action(
        db,
        module="rbac",
        action="user.updated",
        message=f"user #{user_id} updated",
        detail={"user_id": user_id, "fields": sorted(patch.keys())},
    )
    return _load_user_out(db, user_id)


@router.post(
    "/users/batch-update",
    response_model=list[UserOut],
    dependencies=[Depends(require_permission("user.manage"))],
)
def batch_update_users(body: UserBatchUpdateIn, db: Session = Depends(get_db)) -> list[User]:
    patch = body.updates.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="no updates provided")
    user_ids = sorted(set(body.user_ids))
    users = db.query(User).options(selectinload(User.roles)).filter(User.id.in_(user_ids)).all()
    if len(users) != len(user_ids):
        raise HTTPException(status_code=404, detail="one or more users not found")
    for user in users:
        apply_user_admin_update(db, user, patch)
    log_action(
        db,
        module="rbac",
        action="user.batch_updated",
        message=f"{len(user_ids)} users batch updated",
        detail={"user_ids": user_ids, "fields": sorted(patch.keys())},
    )
    return (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.id.in_(user_ids))
        .order_by(User.id.asc())
        .all()
    )


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_permission("user.manage"))])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).options(selectinload(User.roles).selectinload(Role.permissions)).all()


@router.post(
    "/users/{user_id}/roles",
    response_model=UserOut,
    dependencies=[Depends(require_permission("user.manage"))],
)
def assign_user_roles(user_id: int, body: UserAssignRolesIn, db: Session = Depends(get_db)) -> User:
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    roles = db.query(Role).filter(Role.id.in_(body.role_ids)).all() if body.role_ids else []
    user.roles = roles
    db.commit()
    log_action(
        db,
        module="rbac",
        action="user.roles_updated",
        message=f"user #{user_id} roles updated",
        detail={"user_id": user_id, "role_ids": body.role_ids},
    )
    return (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.id == user_id)
        .one()
    )


@router.post("/roles", response_model=RoleOut, dependencies=[Depends(require_permission("role.manage"))])
def create_role(body: RoleCreate, db: Session = Depends(get_db)) -> Role:
    exists = db.query(Role).filter(Role.name == body.name).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="role already exists")
    row = Role(name=body.name, description=body.description)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="rbac",
        action="role.created",
        message=f"role {row.name} created",
        detail={"role_id": row.id},
    )
    return db.query(Role).options(selectinload(Role.permissions)).filter(Role.id == row.id).one()


@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(require_permission("role.manage"))])
def list_roles(db: Session = Depends(get_db)) -> list[Role]:
    return db.query(Role).options(selectinload(Role.permissions)).all()


@router.post(
    "/roles/{role_id}/permissions",
    response_model=RoleOut,
    dependencies=[Depends(require_permission("role.manage"))],
)
def assign_role_permissions(
    role_id: int,
    body: RoleAssignPermissionsIn,
    db: Session = Depends(get_db),
) -> Role:
    role = db.query(Role).options(selectinload(Role.permissions)).filter(Role.id == role_id).one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="role not found")
    permissions = (
        db.query(Permission).filter(Permission.id.in_(body.permission_ids)).all()
        if body.permission_ids
        else []
    )
    role.permissions = permissions
    db.commit()
    log_action(
        db,
        module="rbac",
        action="role.permissions_updated",
        message=f"role #{role_id} permissions updated",
        detail={"role_id": role_id, "permission_ids": body.permission_ids},
    )
    return db.query(Role).options(selectinload(Role.permissions)).filter(Role.id == role_id).one()


@router.post(
    "/permissions",
    response_model=PermissionOut,
    dependencies=[Depends(require_permission("permission.manage"))],
)
def create_permission(body: PermissionCreate, db: Session = Depends(get_db)) -> Permission:
    exists = db.query(Permission).filter(Permission.code == body.code).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="permission already exists")
    row = Permission(code=body.code, description=body.description)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="rbac",
        action="permission.created",
        message=f"permission {row.code} created",
        detail={"permission_id": row.id},
    )
    return row


@router.get(
    "/permissions",
    response_model=list[PermissionOut],
    dependencies=[Depends(require_permission("permission.manage"))],
)
def list_permissions(db: Session = Depends(get_db)) -> list[Permission]:
    return db.query(Permission).order_by(Permission.code.asc()).all()
