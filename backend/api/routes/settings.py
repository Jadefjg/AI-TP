from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.db.session import get_db
from backend.models.entities import SystemSetting
from backend.schemas.dto import SystemSettingCreate, SystemSettingOut
from backend.services.audit_service import log_action
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
        # Prefer SSL when both selected with port 465; otherwise keep STARTTLS for 587.
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


@router.get("", response_model=list[SystemSettingOut], dependencies=[Depends(require_permission("settings.read"))])
def list_settings(db: Session = Depends(get_db)) -> list[SystemSetting]:
    return db.query(SystemSetting).order_by(SystemSetting.key.asc()).all()


@router.post("", response_model=SystemSettingOut, dependencies=[Depends(require_permission("settings.write"))])
def upsert_setting(body: SystemSettingCreate, db: Session = Depends(get_db)) -> SystemSetting:
    row = db.query(SystemSetting).filter(SystemSetting.key == body.key).one_or_none()
    if row:
        row.value = body.value
        row.description = body.description
    else:
        row = SystemSetting(key=body.key, value=body.value, description=body.description)
        db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="settings",
        action="setting.upserted",
        message=f"setting {row.key} updated",
        detail={"setting_id": row.id, "key": row.key},
    )
    return row


@router.delete("/{key}", response_model=dict, dependencies=[Depends(require_permission("settings.write"))])
def delete_setting(key: str, db: Session = Depends(get_db)) -> dict:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="setting not found")
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
