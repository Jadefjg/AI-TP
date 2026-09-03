"""System dictionary management (dropdown enums without hardcoding)."""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from backend.models.entities import Dictionary, DictionaryItem


def list_dictionaries(db: Session, *, active_only: bool = False) -> list[Dictionary]:
    query = db.query(Dictionary).options(selectinload(Dictionary.items))
    if active_only:
        query = query.filter(Dictionary.is_active.is_(True))
    return query.order_by(Dictionary.code.asc()).all()


def get_dictionary(db: Session, code: str) -> Dictionary | None:
    return (
        db.query(Dictionary)
        .options(selectinload(Dictionary.items))
        .filter(Dictionary.code == code)
        .one_or_none()
    )


def upsert_dictionary(
    db: Session,
    *,
    code: str,
    name: str,
    description: str | None = None,
    is_active: bool = True,
) -> Dictionary:
    row = db.query(Dictionary).filter(Dictionary.code == code).one_or_none()
    if row:
        row.name = name
        row.description = description
        row.is_active = is_active
    else:
        row = Dictionary(code=code, name=name, description=description, is_active=is_active)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_dictionary_item(
    db: Session,
    *,
    dictionary_id: int,
    item_key: str,
    item_label: str,
    item_value: str = "",
    sort_order: int = 0,
    is_active: bool = True,
) -> DictionaryItem:
    row = (
        db.query(DictionaryItem)
        .filter(DictionaryItem.dictionary_id == dictionary_id, DictionaryItem.item_key == item_key)
        .one_or_none()
    )
    if row:
        row.item_label = item_label
        row.item_value = item_value
        row.sort_order = sort_order
        row.is_active = is_active
    else:
        row = DictionaryItem(
            dictionary_id=dictionary_id,
            item_key=item_key,
            item_label=item_label,
            item_value=item_value,
            sort_order=sort_order,
            is_active=is_active,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_dictionary(db: Session, dictionary_id: int) -> None:
    row = db.query(Dictionary).filter(Dictionary.id == dictionary_id).one_or_none()
    if not row:
        raise ValueError("dictionary not found")
    db.delete(row)
    db.commit()


def seed_builtin_dictionaries(db: Session) -> None:
    builtins = [
        (
            "alert_severity",
            "告警等级",
            "运维告警严重级别",
            [
                ("critical", "紧急", "critical", 10),
                ("major", "重要", "major", 20),
                ("minor", "提示", "minor", 30),
            ],
        ),
        (
            "job_status",
            "任务状态",
            "通用任务状态枚举",
            [
                ("pending", "待执行", "pending", 10),
                ("running", "执行中", "running", 20),
                ("completed", "已完成", "completed", 30),
                ("failed", "失败", "failed", 40),
                ("skipped", "已跳过", "skipped", 50),
            ],
        ),
    ]
    for code, name, desc, items in builtins:
        dic = upsert_dictionary(db, code=code, name=name, description=desc, is_active=True)
        for key, label, value, sort in items:
            upsert_dictionary_item(
                db,
                dictionary_id=dic.id,
                item_key=key,
                item_label=label,
                item_value=value,
                sort_order=sort,
                is_active=True,
            )
