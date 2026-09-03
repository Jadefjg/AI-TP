from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.models.entities import AuthToken, Permission, Role, User

PBKDF2_ITERATIONS = 200_000

DEFAULT_PERMISSION_SPECS: tuple[tuple[str, str], ...] = (
    ("dashboard.read", "View dashboard summary"),
    ("project.read", "View projects and project runs"),
    ("project.write", "Create and manage projects"),
    ("knowledge.read", "View project knowledge"),
    ("knowledge.write", "Create and delete project knowledge"),
    ("case.read", "View generated cases"),
    ("case.write", "Create, update, delete and import functional cases"),
    ("case.generate", "Generate functional cases"),
    ("ai.read", "View AI outputs and usage"),
    ("ai.execute", "Execute AI modules"),
    ("prompt.read", "View prompt templates"),
    ("prompt.write", "Manage prompt templates"),
    ("worker.read", "View k6 workers and dispatch jobs"),
    ("worker.manage", "Manage k6 worker nodes"),
    ("run.read", "View test runs"),
    ("run.execute", "Start test runs"),
    ("report.read", "Generate and view reports"),
    ("report.send", "Send reports to recipients"),
    ("user.manage", "Manage users"),
    ("role.manage", "Manage roles"),
    ("permission.manage", "Manage permissions"),
    ("logs.read", "View audit logs"),
    ("audit.export", "Export audit logs"),
    ("audit.manage", "Purge audit logs by retention policy"),
    ("org.read", "View organizations and quotas"),
    ("org.write", "Update organization profile"),
    ("org.manage", "Create and manage organizations"),
    ("org.member.read", "View organization members"),
    ("org.member.manage", "Add/remove organization members and roles"),
    ("billing.read", "View organization billing and invoices"),
    ("billing.manage", "Generate invoices and Stripe checkout"),
    ("settings.read", "View system settings"),
    ("settings.write", "Manage system settings"),
    ("system.read", "View system overview"),
    ("ops.read", "View operations overview and health"),
    ("ops.manage", "Manage operations resources"),
    ("dict.read", "View system dictionaries"),
    ("dict.write", "Manage system dictionaries"),
    ("schedule.read", "View scheduled ops jobs"),
    ("schedule.write", "Manage and trigger scheduled ops jobs"),
    ("workbench.read", "View AI workbench sessions"),
    ("workbench.execute", "Chat and apply AI workbench results"),
    ("integration.ci.read", "View CI webhook integration config"),
    ("integration.ci.manage", "Manage CI webhook and trigger test runs"),
)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt, digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return hmac.compare_digest(derived.hex(), digest)


def create_access_token(db: Session, user: User) -> tuple[str, int]:
    settings = get_settings()
    ttl = max(settings.auth_token_ttl_hours, 1) * 3600
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    row = AuthToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    db.add(row)
    db.commit()
    return raw_token, ttl


def revoke_access_token(db: Session, raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = db.query(AuthToken).filter(AuthToken.token_hash == token_hash).one_or_none()
    if not row:
        return
    db.delete(row)
    db.commit()


def get_user_by_access_token(db: Session, raw_token: str) -> User | None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = (
        db.query(AuthToken)
        .options(
            selectinload(AuthToken.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        )
        .filter(AuthToken.token_hash == token_hash)
        .one_or_none()
    )
    if not row:
        return None
    expires_at = _ensure_utc(row.expires_at)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    if not row.user.is_active:
        return None
    return row.user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.username == username)
        .one_or_none()
    )
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def collect_permission_codes(user: User) -> set[str]:
    codes: set[str] = set()
    for role in user.roles:
        if role.name == "admin":
            codes.update(spec[0] for spec in DEFAULT_PERMISSION_SPECS)
        for permission in role.permissions:
            codes.add(permission.code)
    return codes


def user_has_permission(user: User, code: str) -> bool:
    return code in collect_permission_codes(user)


def register_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    email: str | None = None,
) -> User:
    from backend.services.member_service import bind_member_to_organization
    from backend.services.tenant_service import seed_default_organization

    settings = get_settings()
    if not settings.auth_registration_enabled:
        raise ValueError("registration is disabled")

    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username is required")
    if normalized_username == settings.bootstrap_admin_username:
        raise ValueError("username is reserved")

    exists = db.query(User).filter(User.username == normalized_username).one_or_none()
    if exists:
        raise ValueError("username already exists")

    member_role = db.query(Role).filter(Role.name == "member").one_or_none()
    if not member_role:
        seed_auth_defaults(db)
        member_role = db.query(Role).filter(Role.name == "member").one()

    org = seed_default_organization(db)
    user = User(
        username=normalized_username,
        display_name=(display_name or "").strip() or normalized_username,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    bind_member_to_organization(db, org=org, user=user, role_ids=[member_role.id])
    db.commit()
    return (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.id == user.id)
        .one()
    )


def change_user_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("current password is incorrect")
    user.password_hash = hash_password(new_password)
    db.commit()


def seed_auth_defaults(db: Session) -> None:
    permission_by_code: dict[str, Permission] = {}
    changed = False
    for code, description in DEFAULT_PERMISSION_SPECS:
        row = db.query(Permission).filter(Permission.code == code).one_or_none()
        if not row:
            row = Permission(code=code, description=description)
            db.add(row)
            db.flush()
            changed = True
        permission_by_code[code] = row

    admin_role = db.query(Role).options(selectinload(Role.permissions)).filter(Role.name == "admin").one_or_none()
    if not admin_role:
        admin_role = Role(name="admin", description="Platform administrator")
        db.add(admin_role)
        db.flush()
        changed = True
    desired_permissions = list(permission_by_code.values())
    if {item.code for item in admin_role.permissions} != {item.code for item in desired_permissions}:
        admin_role.permissions = desired_permissions
        changed = True

    settings = get_settings()
    admin_user = (
        db.query(User)
        .options(selectinload(User.roles))
        .filter(User.username == settings.bootstrap_admin_username)
        .one_or_none()
    )
    if not admin_user:
        admin_user = User(
            username=settings.bootstrap_admin_username,
            display_name=settings.bootstrap_admin_display_name,
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_active=True,
        )
        db.add(admin_user)
        db.flush()
        changed = True
    elif not admin_user.password_hash:
        admin_user.password_hash = hash_password(settings.bootstrap_admin_password)
        changed = True
    elif (
        settings.bootstrap_admin_sync_password
        and settings.bootstrap_admin_password
        and not verify_password(settings.bootstrap_admin_password, admin_user.password_hash)
    ):
        admin_user.password_hash = hash_password(settings.bootstrap_admin_password)
        changed = True
    if "admin" not in {role.name for role in admin_user.roles}:
        admin_user.roles = [admin_role]
        changed = True
    if admin_user.organization_id is not None:
        admin_user.organization_id = None
        changed = True

    org_admin_codes = {
        "dashboard.read",
        "project.read",
        "project.write",
        "knowledge.read",
        "knowledge.write",
        "case.read",
        "case.write",
        "case.generate",
        "ai.read",
        "ai.execute",
        "workbench.read",
        "workbench.execute",
        "integration.ci.read",
        "integration.ci.manage",
        "prompt.read",
        "run.read",
        "run.execute",
        "report.read",
        "report.send",
        "logs.read",
        "org.read",
        "org.member.read",
        "org.member.manage",
        "billing.read",
        "billing.manage",
        "settings.read",
    }
    member_codes = {
        "dashboard.read",
        "project.read",
        "project.write",
        "knowledge.read",
        "knowledge.write",
        "case.read",
        "case.write",
        "case.generate",
        "ai.read",
        "ai.execute",
        "workbench.read",
        "workbench.execute",
        "integration.ci.read",
        "run.read",
        "run.execute",
        "report.read",
        "report.send",
        "logs.read",
        "org.read",
        "billing.read",
    }
    viewer_codes = {
        "dashboard.read",
        "project.read",
        "knowledge.read",
        "case.read",
        "ai.read",
        "workbench.read",
        "integration.ci.read",
        "run.read",
        "report.read",
        "org.read",
        "billing.read",
    }
    for role_name, codes in (
        ("org_admin", org_admin_codes),
        ("member", member_codes),
        ("viewer", viewer_codes),
    ):
        perms = [permission_by_code[c] for c in codes if c in permission_by_code]
        role = db.query(Role).options(selectinload(Role.permissions)).filter(Role.name == role_name).one_or_none()
        if not role:
            role = Role(name=role_name, description=f"Tenant role: {role_name}")
            db.add(role)
            db.flush()
            changed = True
        if {p.code for p in role.permissions} != {p.code for p in perms}:
            role.permissions = perms
            changed = True

    if changed:
        db.commit()


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
