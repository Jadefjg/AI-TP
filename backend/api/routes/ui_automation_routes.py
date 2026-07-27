from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import Project
from backend.schemas.dto import UiScriptPreviewIn, UiScriptStepExecuteIn, UiScriptUpdateIn
from backend.services.audit_service import log_action
from backend.services.case_service import require_case
from backend.services.engines.ui_playwright import (
    execute_ui_step,
    list_ui_steps,
    steps_from_functional_case,
    steps_to_playwright_code,
)

router = APIRouter(prefix="/projects", tags=["ui-automation"])


@router.post(
    "/{project_id}/ui-automation/preview",
    dependencies=[Depends(require_permission("case.read"))],
)
def preview_ui_script(
    body: UiScriptPreviewIn,
    project: Project = Depends(get_tenant_project),
) -> dict:
    _ = project
    return list_ui_steps(body.ui_script, base_url=body.base_url)


@router.post(
    "/{project_id}/ui-automation/execute-step",
    dependencies=[Depends(require_permission("case.write"))],
)
def execute_ui_single_step(
    body: UiScriptStepExecuteIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    result = execute_ui_step(body.ui_script, body.step_index, base_url=body.base_url)
    log_action(
        db,
        module="ui_automation",
        action="ui.step_executed",
        message=f"project #{project.id} ui step {body.step_index}",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"step_index": body.step_index, "status": result.get("status")},
    )
    return result


@router.get(
    "/{project_id}/ui-automation/cases/{case_id}/script",
    dependencies=[Depends(require_permission("case.read"))],
)
def get_case_ui_script(
    case_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_case(db, project.id, case_id)
    doc = steps_from_functional_case(row)
    code = steps_to_playwright_code(doc)
    return {"case_id": row.id, "ui_script": row.ui_script or doc, "playwright_code": code}


@router.put(
    "/{project_id}/ui-automation/cases/{case_id}/script",
    dependencies=[Depends(require_permission("case.write"))],
)
def update_case_ui_script(
    case_id: int,
    body: UiScriptUpdateIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_case(db, project.id, case_id)
    row.ui_script = body.ui_script
    db.commit()
    db.refresh(row)
    log_action(
        db,
        module="ui_automation",
        action="ui.script_updated",
        message=f"case #{case_id} ui_script updated",
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return {"case_id": row.id, "ui_script": row.ui_script}


@router.post(
    "/{project_id}/ui-automation/cases/{case_id}/generate-from-case",
    dependencies=[Depends(require_permission("case.write"))],
)
def generate_ui_from_case(
    case_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_case(db, project.id, case_id)
    doc = steps_from_functional_case(row, force_rebuild=True)
    if not doc.get("steps"):
        raise HTTPException(status_code=400, detail="当前用例没有可转换的步骤，请先完善功能用例")
    row.ui_script = doc
    db.commit()
    log_action(
        db,
        module="ui_automation",
        action="ui.generated_from_case",
        message=f"case #{case_id} ui_script generated from functional steps",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"steps": len(doc.get("steps") or [])},
    )
    return {"case_id": row.id, "ui_script": doc}
