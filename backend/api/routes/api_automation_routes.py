from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import ApiRegressionSet, Project
from backend.schemas.dto import (
    ApiRegressionSetCreate,
    ApiRegressionSetOut,
    DslPreviewIn,
    DslStepExecuteIn,
)
from backend.services.audit_service import log_action
from backend.services.engines.api_automation import execute_dsl_step, list_dsl_steps

router = APIRouter(prefix="/projects", tags=["api-automation"])


@router.get(
    "/{project_id}/api-regression-sets",
    response_model=list[ApiRegressionSetOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_regression_sets(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[ApiRegressionSet]:
    return (
        db.query(ApiRegressionSet)
        .filter(ApiRegressionSet.project_id == project.id)
        .order_by(ApiRegressionSet.id.desc())
        .all()
    )


@router.post(
    "/{project_id}/api-regression-sets",
    response_model=ApiRegressionSetOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def create_regression_set(
    body: ApiRegressionSetCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> ApiRegressionSet:
    row = ApiRegressionSet(
        project_id=project.id,
        name=body.name,
        description=body.description,
        case_ids=body.case_ids,
        base_url=body.base_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="api_automation",
        action="regression_set.created",
        message=f"regression set #{row.id} created",
        detail={"project_id": project.id, "case_ids": body.case_ids},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return row


@router.delete(
    "/{project_id}/api-regression-sets/{set_id}",
    dependencies=[Depends(require_permission("ai.execute"))],
)
def delete_regression_set(
    set_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(ApiRegressionSet)
        .filter(ApiRegressionSet.id == set_id, ApiRegressionSet.project_id == project.id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="regression set not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "set_id": set_id}


@router.post(
    "/{project_id}/api-automation/dsl/preview",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.read"))],
)
def preview_dsl(
    body: DslPreviewIn,
    project: Project = Depends(get_tenant_project),
) -> dict:
    _ = project
    return list_dsl_steps(body.script_content, base_url=body.base_url)


@router.post(
    "/{project_id}/api-automation/dsl/execute-step",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def execute_dsl_single_step(
    body: DslStepExecuteIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    result = execute_dsl_step(
        body.script_content,
        body.step_index,
        base_url=body.base_url,
    )
    log_action(
        db,
        module="api_automation",
        action="dsl.step_executed",
        message=f"project #{project.id} step {body.step_index}",
        detail={"step_index": body.step_index, "status": result.get("status")},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return result
