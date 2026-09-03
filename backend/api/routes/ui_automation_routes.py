from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_any_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import Project
from backend.schemas.dto import UiScriptPreviewIn, UiScriptStepExecuteIn, UiScriptUpdateIn
from backend.services.agents import ui_agent
from backend.services.audit_service import log_action
from backend.services.case_service import require_case
from backend.services.engines.ui_playwright import steps_from_functional_case, steps_to_playwright_code

router = APIRouter(prefix="/projects", tags=["ui-automation"])

# Align with pipeline Agents: ai.* preferred; keep case.* for legacy roles.
_UI_READ = Depends(require_any_permission("ai.read", "case.read"))
_UI_WRITE = Depends(require_any_permission("ai.execute", "case.write"))


@router.post(
    "/{project_id}/ui-automation/preview",
    dependencies=[_UI_READ],
)
def preview_ui_script(
    body: UiScriptPreviewIn,
    project: Project = Depends(get_tenant_project),
) -> dict:
    _ = project
    return ui_agent.preview(body.ui_script, base_url=body.base_url)


@router.post(
    "/{project_id}/ui-automation/execute-step",
    dependencies=[_UI_WRITE],
)
def execute_ui_single_step(
    body: UiScriptStepExecuteIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    result = ui_agent.execute_step(body.ui_script, body.step_index, base_url=body.base_url)
    log_action(
        db,
        module="agents",
        action="ui_agent.step",
        message=f"project #{project.id} ui step {body.step_index}",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"step_index": body.step_index, "status": result.get("status")},
    )
    return result


@router.post(
    "/{project_id}/ui-automation/execute-agent",
    dependencies=[_UI_WRITE],
)
def execute_ui_gui_agent(
    body: UiScriptPreviewIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    result = ui_agent.execute(body.ui_script, base_url=body.base_url)
    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
    log_action(
        db,
        module="agents",
        action="ui_agent.execute",
        message=f"project #{project.id} playwright gui agent",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"status": result.get("status"), "steps": detail.get("steps")},
    )
    return result


@router.get(
    "/{project_id}/ui-automation/cases/{case_id}/script",
    dependencies=[_UI_READ],
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
    dependencies=[_UI_WRITE],
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
        module="agents",
        action="ui_agent.script_updated",
        message=f"case #{case_id} ui_script updated",
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return {"case_id": row.id, "ui_script": row.ui_script}


@router.post(
    "/{project_id}/ui-automation/cases/{case_id}/generate-from-case",
    dependencies=[_UI_WRITE],
)
def generate_ui_from_case(
    case_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = ui_agent.generate(db, project, case_id=case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_action(
        db,
        module="agents",
        action="ui_agent.generate",
        message=f"case #{case_id} ui_script generated from functional steps",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"steps": len((result.get("ui_script") or {}).get("steps") or [])},
    )
    return result
