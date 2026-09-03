"""System setting revision history and rollback."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.entities import SettingRevision, SystemSetting, User
from backend.services.audit_service import log_action


def record_setting_revision(
    db: Session,
    *,
    setting_key: str,
    old_value: str | None,
    new_value: str | None,
    description: str | None,
    change_type: str,
    actor: User | None,
) -> SettingRevision:
    row = SettingRevision(
        setting_key=setting_key,
        old_value=old_value,
        new_value=new_value,
        description=description,
        change_type=change_type,
        actor_user_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    return row


def list_setting_revisions(db: Session, *, key: str | None = None, limit: int = 50) -> list[SettingRevision]:
    query = db.query(SettingRevision)
    if key:
        query = query.filter(SettingRevision.setting_key == key)
    return query.order_by(SettingRevision.id.desc()).limit(max(1, min(limit, 200))).all()


def rollback_setting_revision(
    db: Session,
    *,
    revision_id: int,
    actor: User | None,
) -> SystemSetting:
    rev = db.query(SettingRevision).filter(SettingRevision.id == revision_id).one_or_none()
    if not rev:
        raise ValueError("revision not found")
    if rev.old_value is None and rev.change_type == "create":
        # Rolling back a create deletes the setting.
        row = db.query(SystemSetting).filter(SystemSetting.key == rev.setting_key).one_or_none()
        if row:
            record_setting_revision(
                db,
                setting_key=rev.setting_key,
                old_value=row.value,
                new_value=None,
                description=row.description,
                change_type="rollback_delete",
                actor=actor,
            )
            db.delete(row)
            db.commit()
            log_action(
                db,
                module="settings",
                action="setting.rollback_delete",
                message=f"setting {rev.setting_key} deleted via rollback #{revision_id}",
                detail={"revision_id": revision_id, "key": rev.setting_key},
            )
            raise ValueError("setting deleted by rollback")
        raise ValueError("setting already absent")

    row = db.query(SystemSetting).filter(SystemSetting.key == rev.setting_key).one_or_none()
    restore_value = rev.old_value if rev.old_value is not None else ""
    if row:
        old = row.value
        row.value = restore_value
        if rev.description is not None:
            row.description = rev.description
    else:
        old = None
        row = SystemSetting(key=rev.setting_key, value=restore_value, description=rev.description)
        db.add(row)
    record_setting_revision(
        db,
        setting_key=rev.setting_key,
        old_value=old,
        new_value=restore_value,
        description=rev.description,
        change_type="rollback",
        actor=actor,
    )
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="settings",
        action="setting.rollback",
        message=f"setting {rev.setting_key} rolled back via #{revision_id}",
        detail={"revision_id": revision_id, "key": rev.setting_key},
    )
    return row
