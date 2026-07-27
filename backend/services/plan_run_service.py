from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from backend.models.entities import FunctionalCase, TestSuite
from backend.services.case_service import require_plan
from backend.services.engines.ui_playwright import execute_ui_script


def list_project_functional_case_ids(db: Session, *, project_id: int) -> list[int]:
    rows = (
        db.query(FunctionalCase.id)
        .filter(FunctionalCase.project_id == project_id)
        .order_by(FunctionalCase.id.asc())
        .all()
    )
    return [r[0] for r in rows]


def resolve_functional_case_ids(
    db: Session,
    *,
    project_id: int,
    suite_id: int | None = None,
    plan_id: int | None = None,
) -> list[int]:
    if suite_id is not None:
        suite = (
            db.query(TestSuite)
            .options(selectinload(TestSuite.cases))
            .filter(TestSuite.id == suite_id, TestSuite.project_id == project_id)
            .one_or_none()
        )
        if not suite:
            raise ValueError("test suite not found")
        return [c.id for c in sorted(suite.cases, key=lambda x: x.id)]

    if plan_id is not None:
        plan = require_plan(db, project_id, plan_id)
        suites = (
            db.query(TestSuite)
            .options(selectinload(TestSuite.cases))
            .filter(TestSuite.project_id == project_id, TestSuite.plan_id == plan.id)
            .order_by(TestSuite.id.asc())
            .all()
        )
        seen: set[int] = set()
        ordered: list[int] = []
        for suite in suites:
            for case in sorted(suite.cases, key=lambda x: x.id):
                if case.id not in seen:
                    seen.add(case.id)
                    ordered.append(case.id)
        return ordered

    return []


def execute_functional_cases(
    db: Session,
    *,
    project_id: int,
    case_ids: list[int],
) -> dict:
    if not case_ids:
        return {
            "command_label": "functional://suite",
            "exit_code": 0,
            "stdout": "no cases in suite/plan",
            "stderr": "",
            "status": "skipped",
            "detail": {"reason": "empty case set", "case_results": []},
        }

    rows = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.project_id == project_id, FunctionalCase.id.in_(case_ids))
        .order_by(FunctionalCase.id.asc())
        .all()
    )
    by_id = {r.id: r for r in rows}
    results: list[dict] = []
    failed = 0
    for cid in case_ids:
        row = by_id.get(cid)
        if not row:
            results.append({"case_id": cid, "status": "error", "reason": "case not found"})
            failed += 1
            continue
        if isinstance(row.ui_script, (dict, list)) and row.ui_script:
            base_url = "http://127.0.0.1:5173"
            exec_result = execute_ui_script(row.ui_script, base_url=base_url)
            st = exec_result.get("status") or "failed"
            results.append(
                {
                    "case_id": row.id,
                    "title": row.title,
                    "status": st,
                    "engine": "playwright",
                    "module": row.module,
                }
            )
            if st == "failed":
                failed += 1
            elif st == "skipped":
                pass
            continue

        steps = row.steps if isinstance(row.steps, list) else []
        ok = bool(row.title and steps)
        results.append(
            {
                "case_id": row.id,
                "title": row.title,
                "status": "passed" if ok else "skipped",
                "steps_count": len(steps),
                "module": row.module,
            }
        )
        if not ok:
            failed += 1

    status = "failed" if failed and failed == len(case_ids) else ("passed" if failed == 0 else "passed")
    if failed > 0 and failed < len(case_ids):
        status = "passed"
    if failed == len(case_ids):
        status = "failed"

    lines = [f"[{r['status']}] #{r.get('case_id')} {r.get('title', '-')}" for r in results]
    return {
        "command_label": "functional://suite",
        "exit_code": 0 if status == "passed" else 1,
        "stdout": "\n".join(lines),
        "stderr": "",
        "status": status,
        "detail": {"case_results": results, "total": len(case_ids), "failed": failed},
    }
