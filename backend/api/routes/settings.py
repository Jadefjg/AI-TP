from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_permission
from backend.db.session import get_db
from backend.models.entities import SystemSetting, User
from backend.schemas.dto import SettingRevisionOut, SystemSettingCreate, SystemSettingOut
from backend.services.audit_service import log_action
from backend.services.setting_revision_service import (
    list_setting_revisions,
    record_setting_revision,
    rollback_setting_revision,
)
from backend.services.smtp_config import resolve_smtp_config, smtp_public_view, upsert_smtp_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SmtpSettingsIn(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = None
    password: str | None = None
    use_tls: bool | None = None
    use_ssl: bool | None = None
    from_addr: str | None = None
    dry_run: bool | None = None


@router.get("/smtp", dependencies=[Depends(require_permission("settings.read"))])
def get_smtp_settings(db: Session = Depends(get_db)) -> dict:
    return smtp_public_view(resolve_smtp_config(db))


@router.put("/smtp", dependencies=[Depends(require_permission("settings.write"))])
def update_smtp_settings(body: SmtpSettingsIn, db: Session = Depends(get_db)) -> dict:
    payload = body.model_dump(exclude_unset=True)
    host = str(payload.get("host") or "").strip().lower()
    user = str(payload.get("user") or "").strip()
    if host and "qq.com" in host and user and "@" not in user:
        raise HTTPException(
            status_code=400,
            detail="QQ 邮箱 SMTP 用户名须为完整邮箱（如 name@qq.com），不能填 admin 等登录名",
        )
    if payload.get("use_ssl") and payload.get("use_tls"):
        port = payload.get("port")
        if port == 465:
            payload["use_tls"] = False
        elif port == 587:
            payload["use_ssl"] = False
    cfg = upsert_smtp_settings(db, payload)
    log_action(
        db,
        module="settings",
        action="smtp.updated",
        message="smtp settings updated",
        detail={"configured": cfg.configured, "host": cfg.host, "port": cfg.port},
    )
    return smtp_public_view(cfg)


@router.get("/revisions", response_model=list[SettingRevisionOut], dependencies=[Depends(require_permission("settings.read"))])
def setting_revisions(
    key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list:
    return list_setting_revisions(db, key=key, limit=limit)


@router.post(
    "/revisions/{revision_id}/rollback",
    dependencies=[Depends(require_permission("settings.write"))],
)
def setting_rollback(
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = rollback_setting_revision(db, revision_id=revision_id, actor=user)
        return {"ok": True, "setting": SystemSettingOut.model_validate(row).model_dump()}
    except ValueError as exc:
        detail = str(exc)
        if "deleted by rollback" in detail:
            return {"ok": True, "deleted": True, "detail": detail}
        raise HTTPException(status_code=400, detail=detail) from exc


@router.get("", response_model=list[SystemSettingOut], dependencies=[Depends(require_permission("settings.read"))])
def list_settings(db: Session = Depends(get_db)) -> list[SystemSetting]:
    return db.query(SystemSetting).order_by(SystemSetting.key.asc()).all()


@router.post("", response_model=SystemSettingOut, dependencies=[Depends(require_permission("settings.write"))])
def upsert_setting(
    body: SystemSettingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SystemSetting:
    row = db.query(SystemSetting).filter(SystemSetting.key == body.key).one_or_none()
    if row:
        old_value = row.value
        change_type = "update"
        row.value = body.value
        row.description = body.description
    else:
        old_value = None
        change_type = "create"
        row = SystemSetting(key=body.key, value=body.value, description=body.description)
        db.add(row)
    record_setting_revision(
        db,
        setting_key=body.key,
        old_value=old_value,
        new_value=body.value,
        description=body.description,
        change_type=change_type,
        actor=user,
    )
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="settings",
        action="setting.upserted",
        message=f"setting {row.key} updated",
        detail={"setting_id": row.id, "key": row.key, "old_value": old_value, "new_value": body.value},
    )
    return row


@router.delete("/{key}", response_model=dict, dependencies=[Depends(require_permission("settings.write"))])
def delete_setting(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="setting not found")
    record_setting_revision(
        db,
        setting_key=key,
        old_value=row.value,
        new_value=None,
        description=row.description,
        change_type="delete",
        actor=user,
    )
    db.delete(row)
    db.commit()
    log_action(
        db,
        module="settings",
        action="setting.deleted",
        message=f"setting {key} deleted",
        detail={"key": key},
    )
    return {"ok": True, "deleted_key": key}
