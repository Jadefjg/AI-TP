from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import FunctionalCase, RequirementReview

SECTION_LABELS: dict[str, str] = {
    "ambiguity_list": "需求歧义",
    "miss_logic_list": "逻辑缺失",
    "untestable_list": "可测性缺陷",
    "biz_risk_list": "业务风险",
}

LIST_KEYS = tuple(SECTION_LABELS.keys())


def _priority_from_level(level: str | None) -> str:
    lv = (level or "").strip()
    if lv in {"高", "high", "High"}:
        return "high"
    if lv in {"低", "low", "Low"}:
        return "low"
    return "medium"


def _steps_from_suggest(suggest: str | None) -> list[str]:
    text = (suggest or "").strip()
    if not text:
        return ["根据评审建议执行验证"]
    parts = [p.strip() for p in text.replace("\n", "；").split("；") if p.strip()]
    return parts or [text]


def flatten_review_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in LIST_KEYS:
        for row in payload.get(key) or []:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "category": key,
                    "category_label": SECTION_LABELS[key],
                    "pos": str(row.get("pos") or ""),
                    "level": str(row.get("level") or ""),
                    "desc": str(row.get("desc") or ""),
                    "suggest": str(row.get("suggest") or ""),
                }
            )
    return items


def _item_key(item: dict[str, Any]) -> str:
    return f"{item.get('category')}|{item.get('pos')}|{item.get('desc')}"


def diff_requirement_reviews(
    older: RequirementReview,
    newer: RequirementReview,
) -> dict[str, Any]:
    old_items = {_item_key(x): x for x in flatten_review_items(older.result_json or {})}
    new_items = {_item_key(x): x for x in flatten_review_items(newer.result_json or {})}

    added = [new_items[k] for k in new_items if k not in old_items]
    removed = [old_items[k] for k in old_items if k not in new_items]
    changed: list[dict[str, Any]] = []
    for key in new_items:
        if key not in old_items:
            continue
        o, n = old_items[key], new_items[key]
        if o.get("level") != n.get("level") or o.get("suggest") != n.get("suggest"):
            changed.append({"before": o, "after": n})

    return {
        "from_review_id": older.id,
        "to_review_id": newer.id,
        "from_created_at": str(older.created_at),
        "to_created_at": str(newer.created_at),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def persist_requirement_review(
    db: Session,
    *,
    project_id: int,
    requirement_text: str,
    result_json: dict[str, Any],
    model_name: str,
    prompt_template_id: int | None = None,
    source_filename: str | None = None,
    source_format: str | None = None,
) -> RequirementReview:
    review = RequirementReview(
        project_id=project_id,
        requirement_text=requirement_text[:50000],
        result_json=result_json,
        model_name=model_name,
        prompt_template_id=prompt_template_id,
        source_filename=source_filename,
        source_format=source_format,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def convert_review_to_cases(
    db: Session,
    review: RequirementReview,
    *,
    sections: list[str] | None = None,
) -> tuple[list[FunctionalCase], int | None]:
    from backend.services.case_service import append_cases_to_suite, ensure_pipeline_suite

    payload = review.result_json if isinstance(review.result_json, dict) else {}
    chosen = [s for s in (sections or LIST_KEYS) if s in LIST_KEYS]
    created: list[FunctionalCase] = []

    for key in chosen:
        label = SECTION_LABELS[key]
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            desc = str(item.get("desc") or "评审项")
            pos = str(item.get("pos") or "")
            title = f"[{label}] {pos}: {desc}"[:512]
            row = FunctionalCase(
                project_id=review.project_id,
                title=title,
                module=label,
                preconditions=f"来源评审 #{review.id}",
                steps=_steps_from_suggest(str(item.get("suggest") or "")),
                expected="评审问题已修复或已确认接受风险",
                priority=_priority_from_level(str(item.get("level") or "")),
                source_requirement=review.requirement_text[:20000],
            )
            db.add(row)
            created.append(row)

    db.flush()
    suite_id: int | None = None
    if created:
        suite = ensure_pipeline_suite(db, review.project_id)
        append_cases_to_suite(db, suite, [row.id for row in created])
        suite_id = suite.id
    db.commit()
    for row in created:
        db.refresh(row)
    return created, suite_id
