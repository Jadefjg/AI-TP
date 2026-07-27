from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import FunctionalCase, Project, TestPlan, TestSuite
from backend.schemas.dto import (
    SuiteAssignCasesIn,
    TestPlanCreate,
    TestPlanOut,
    TestPlanUpdate,
    TestSuiteCreate,
    TestSuiteOut,
    TestSuiteUpdate,
    FunctionalCaseOut,
)
from backend.services.audit_service import log_action
from backend.services.case_service import (
    assign_cases_to_suite,
    require_plan,
    require_suite,
)

router = APIRouter(prefix="/projects", tags=["test-organization"])


def _suite_out(suite: TestSuite) -> TestSuiteOut:
    return TestSuiteOut(
        id=suite.id,
        project_id=suite.project_id,
        plan_id=suite.plan_id,
        name=suite.name,
        description=suite.description,
        created_at=suite.created_at,
        case_count=len(suite.cases or []),
    )


@router.get(
    "/{project_id}/test-plans",
    response_model=list[TestPlanOut],
    dependencies=[Depends(require_permission("case.read"))],
)
def list_test_plans(project: Project = Depends(get_tenant_project), db: Session = Depends(get_db)) -> list[TestPlan]:
    return (
        db.query(TestPlan)
        .filter(TestPlan.project_id == project.id)
        .order_by(TestPlan.id.desc())
        .all()
    )


@router.post(
    "/{project_id}/test-plans",
    response_model=TestPlanOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def create_test_plan(
    body: TestPlanCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> TestPlan:
    row = TestPlan(
        project_id=project.id,
        name=body.name,
        description=body.description,
        status=body.status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="cases",
        action="test_plan.created",
        message=f"created test plan #{row.id}",
        detail={"project_id": project.id, "plan_id": row.id},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return row


@router.patch(
    "/{project_id}/test-plans/{plan_id}",
    response_model=TestPlanOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def update_test_plan(
    plan_id: int,
    body: TestPlanUpdate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> TestPlan:
    row = require_plan(db, project.id, plan_id)
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.status is not None:
        row.status = body.status
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/{project_id}/test-plans/{plan_id}",
    dependencies=[Depends(require_permission("case.write"))],
)
def delete_test_plan(
    plan_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_plan(db, project.id, plan_id)
    for suite in list(row.suites or []):
        suite.plan_id = None
    db.delete(row)
    db.commit()
    return {"deleted": True, "plan_id": plan_id}


@router.get(
    "/{project_id}/test-suites",
    response_model=list[TestSuiteOut],
    dependencies=[Depends(require_permission("case.read"))],
)
def list_test_suites(project: Project = Depends(get_tenant_project), db: Session = Depends(get_db)) -> list[TestSuiteOut]:
    rows = (
        db.query(TestSuite)
        .filter(TestSuite.project_id == project.id)
        .order_by(TestSuite.id.desc())
        .all()
    )
    return [_suite_out(row) for row in rows]


@router.post(
    "/{project_id}/test-suites",
    response_model=TestSuiteOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def create_test_suite(
    body: TestSuiteCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> TestSuiteOut:
    if body.plan_id is not None:
        require_plan(db, project.id, body.plan_id)
    row = TestSuite(
        project_id=project.id,
        plan_id=body.plan_id,
        name=body.name,
        description=body.description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _suite_out(row)


@router.patch(
    "/{project_id}/test-suites/{suite_id}",
    response_model=TestSuiteOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def update_test_suite(
    suite_id: int,
    body: TestSuiteUpdate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> TestSuiteOut:
    row = require_suite(db, project.id, suite_id)
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.plan_id is not None:
        require_plan(db, project.id, body.plan_id)
        row.plan_id = body.plan_id
    db.commit()
    db.refresh(row)
    return _suite_out(row)


@router.delete(
    "/{project_id}/test-suites/{suite_id}",
    dependencies=[Depends(require_permission("case.write"))],
)
def delete_test_suite(
    suite_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_suite(db, project.id, suite_id)
    db.delete(row)
    db.commit()
    return {"deleted": True, "suite_id": suite_id}


@router.get(
    "/{project_id}/test-suites/{suite_id}/cases",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_permission("case.read"))],
)
def list_suite_cases(
    suite_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    row = require_suite(db, project.id, suite_id)
    return list(row.cases or [])


@router.put(
    "/{project_id}/test-suites/{suite_id}/cases",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_permission("case.write"))],
)
def assign_suite_cases(
    suite_id: int,
    body: SuiteAssignCasesIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    suite = require_suite(db, project.id, suite_id)
    cases = assign_cases_to_suite(db, suite, body.case_ids)
    db.commit()
    return cases
