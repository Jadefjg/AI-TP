from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.entities import FunctionalCase, Project, TestPlan, TestSuite


def require_project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def require_case(db: Session, project_id: int, case_id: int) -> FunctionalCase:
    row = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.id == case_id, FunctionalCase.project_id == project_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    return row


def case_to_export_dict(row: FunctionalCase) -> dict:
    return {
        "title": row.title,
        "module": row.module,
        "preconditions": row.preconditions,
        "steps": row.steps or [],
        "expected": row.expected,
        "priority": row.priority,
        "source_requirement": row.source_requirement,
        "openapi_operation_id": row.openapi_operation_id,
    }


def create_case_row(db: Session, project_id: int, payload: dict) -> FunctionalCase:
    row = FunctionalCase(
        project_id=project_id,
        title=payload["title"],
        module=payload.get("module"),
        preconditions=payload.get("preconditions"),
        steps=payload.get("steps") or [],
        expected=payload.get("expected"),
        priority=payload.get("priority") or "medium",
        source_requirement=payload.get("source_requirement"),
        openapi_operation_id=payload.get("openapi_operation_id"),
    )
    db.add(row)
    db.flush()
    return row


def apply_case_update(row: FunctionalCase, payload: dict) -> None:
    for field in (
        "title",
        "module",
        "preconditions",
        "steps",
        "expected",
        "priority",
        "source_requirement",
        "openapi_operation_id",
        "ui_script",
    ):
        if field in payload and payload[field] is not None:
            setattr(row, field, payload[field])
    row.updated_at = datetime.now(timezone.utc)


def require_plan(db: Session, project_id: int, plan_id: int) -> TestPlan:
    row = (
        db.query(TestPlan)
        .filter(TestPlan.id == plan_id, TestPlan.project_id == project_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="test plan not found")
    return row


def require_suite(db: Session, project_id: int, suite_id: int) -> TestSuite:
    row = (
        db.query(TestSuite)
        .filter(TestSuite.id == suite_id, TestSuite.project_id == project_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="test suite not found")
    return row


def assign_cases_to_suite(db: Session, suite: TestSuite, case_ids: list[int]) -> list[FunctionalCase]:
    if not case_ids:
        suite.cases = []
        db.flush()
        return []
    rows = (
        db.query(FunctionalCase)
        .filter(
            FunctionalCase.project_id == suite.project_id,
            FunctionalCase.id.in_(case_ids),
        )
        .all()
    )
    found_ids = {row.id for row in rows}
    missing = [cid for cid in case_ids if cid not in found_ids]
    if missing:
        raise HTTPException(status_code=400, detail=f"cases not found in project: {missing}")
    id_to_row = {row.id: row for row in rows}
    suite.cases = [id_to_row[cid] for cid in case_ids]
    db.flush()
    return suite.cases


PIPELINE_SUITE_NAME = "智能流水 · 自动套件"


def ensure_pipeline_suite(db: Session, project_id: int) -> TestSuite:
    """Ensure a default suite exists so converted/generated cases can run via functional kind."""
    from sqlalchemy.orm import selectinload

    row = (
        db.query(TestSuite)
        .options(selectinload(TestSuite.cases))
        .filter(TestSuite.project_id == project_id, TestSuite.name == PIPELINE_SUITE_NAME)
        .order_by(TestSuite.id.asc())
        .first()
    )
    if row:
        return row
    row = TestSuite(
        project_id=project_id,
        name=PIPELINE_SUITE_NAME,
        description="智能流水自动维护：转用例/生成用例时挂载，便于直接发起 functional Run",
    )
    db.add(row)
    db.flush()
    return row


def append_cases_to_suite(db: Session, suite: TestSuite, case_ids: list[int]) -> list[FunctionalCase]:
    """Append cases to a suite without removing existing members."""
    from sqlalchemy.orm import selectinload

    if not case_ids:
        return list(suite.cases or [])
    suite = (
        db.query(TestSuite)
        .options(selectinload(TestSuite.cases))
        .filter(TestSuite.id == suite.id)
        .one()
    )
    existing = list(suite.cases or [])
    existing_ids = {row.id for row in existing}
    to_add = [cid for cid in case_ids if cid not in existing_ids]
    if not to_add:
        return existing
    rows = (
        db.query(FunctionalCase)
        .filter(
            FunctionalCase.project_id == suite.project_id,
            FunctionalCase.id.in_(to_add),
        )
        .all()
    )
    found_ids = {row.id for row in rows}
    missing = [cid for cid in to_add if cid not in found_ids]
    if missing:
        raise HTTPException(status_code=400, detail=f"cases not found in project: {missing}")
    id_to_row = {row.id: row for row in rows}
    suite.cases = existing + [id_to_row[cid] for cid in to_add]
    db.flush()
    return list(suite.cases)
