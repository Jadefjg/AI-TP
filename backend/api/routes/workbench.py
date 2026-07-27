from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import AiWorkbenchMessage, AiWorkbenchSession, Project
from backend.schemas.dto import (
    WorkbenchChatIn,
    WorkbenchChatOut,
    WorkbenchMessageOut,
    WorkbenchSessionCreate,
    WorkbenchSessionOut,
)
from backend.services.audit_service import log_action
from backend.services import workbench_service

router = APIRouter(prefix="/projects", tags=["workbench"])


def _session(db: Session, project_id: int, session_id: int) -> AiWorkbenchSession:
    row = (
        db.query(AiWorkbenchSession)
        .filter(AiWorkbenchSession.id == session_id, AiWorkbenchSession.project_id == project_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="workbench session not found")
    return row


@router.get(
    "/{project_id}/workbench/sessions",
    response_model=list[WorkbenchSessionOut],
    dependencies=[Depends(require_permission("workbench.read"))],
)
def list_sessions(project: Project = Depends(get_tenant_project), db: Session = Depends(get_db)) -> list:
    return (
        db.query(AiWorkbenchSession)
        .filter(AiWorkbenchSession.project_id == project.id)
        .order_by(AiWorkbenchSession.id.desc())
        .limit(50)
        .all()
    )


@router.post(
    "/{project_id}/workbench/sessions",
    response_model=WorkbenchSessionOut,
    dependencies=[Depends(require_permission("workbench.execute"))],
)
async def create_session(
    body: WorkbenchSessionCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiWorkbenchSession:
    row = await workbench_service.create_session(
        db,
        project=project,
        module_type=body.module_type,
        title=body.title,
    )
    log_action(
        db,
        module="workbench",
        action="session.created",
        message=f"workbench session #{row.id}",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"module_type": body.module_type},
    )
    return row


@router.get(
    "/{project_id}/workbench/sessions/{session_id}/messages",
    response_model=list[WorkbenchMessageOut],
    dependencies=[Depends(require_permission("workbench.read"))],
)
def list_messages(
    session_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list:
    _session(db, project.id, session_id)
    return (
        db.query(AiWorkbenchMessage)
        .filter(AiWorkbenchMessage.session_id == session_id)
        .order_by(AiWorkbenchMessage.id.asc())
        .all()
    )


@router.post(
    "/{project_id}/workbench/sessions/{session_id}/chat",
    response_model=WorkbenchChatOut,
    dependencies=[Depends(require_permission("workbench.execute"))],
)
async def chat(
    session_id: int,
    body: WorkbenchChatIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    sess = _session(db, project.id, session_id)
    user_row, assistant_row = await workbench_service.chat_in_session(
        db,
        session=sess,
        project=project,
        user_message=body.message,
        use_rag=body.use_rag,
        variables=body.variables,
    )
    log_action(
        db,
        module="workbench",
        action="session.chat",
        message=f"workbench chat session #{session_id}",
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return {
        "user": WorkbenchMessageOut.model_validate(user_row),
        "assistant": WorkbenchMessageOut.model_validate(assistant_row),
    }


@router.post(
    "/{project_id}/workbench/sessions/{session_id}/apply",
    dependencies=[Depends(require_permission("workbench.execute"))],
)
async def apply_result(
    session_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    sess = _session(db, project.id, session_id)
    result = await workbench_service.apply_session_result(db, session=sess, project=project)
    log_action(
        db,
        module="workbench",
        action="session.applied",
        message=f"workbench apply session #{session_id}",
        organization_id=project.organization_id,
        project_id=project.id,
        detail=result,
    )
    return result
