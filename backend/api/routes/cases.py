import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.api.auth import require_any_permission, require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import FunctionalCase, Project
from backend.schemas.dto import (
    AgentGenerateOut,
    FunctionalCaseBatchImport,
    FunctionalCaseCreate,
    FunctionalCaseOut,
    FunctionalCaseUpdate,
    OpenApiImportIn,
    RequirementIn,
)
from backend.services.agents import requirement_agent
from backend.services.audit_service import log_action
from backend.services.case_service import (
    apply_case_update,
    case_to_export_dict,
    create_case_row,
    require_case,
)
from backend.services.openapi_case_builder import build_case_skeletons, parse_openapi_content
from backend.services.rag_service import retrieve_context_chunks_async
from backend.services.testcase_generator import generate_and_persist

router = APIRouter(prefix="/projects", tags=["functional-cases"])


@router.post(
    "/{project_id}/functional-cases/generate",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_permission("case.generate"))],
)
async def generate_cases(
    body: RequirementIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    try:
        chunks = await retrieve_context_chunks_async(db, project_id=project.id, query=body.requirement_text)
        cases = await generate_and_persist(
            db,
            project,
            body.requirement_text,
            context_chunks=[c.content for c in chunks] if chunks else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_action(
        db,
        module="cases",
        action="cases.generated",
        message=f"generated {len(cases)} cases for project #{project.id}",
        detail={"project_id": project.id, "mode": "basic", "count": len(cases)},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return cases


@router.post(
    "/{project_id}/functional-cases/generate-agent",
    response_model=AgentGenerateOut,
    dependencies=[Depends(require_permission("case.generate"))],
)
async def generate_cases_agent(
    body: RequirementIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AgentGenerateOut:
    try:
        result = await requirement_agent.generate_cases(db, project, body.requirement_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_action(
        db,
        module="cases",
        action="cases.generated_agent",
        message=f"generated {len(result.cases)} agent cases for project #{project.id}",
        detail={
            "project_id": project.id,
            "mode": "agent",
            "count": len(result.cases),
            "contexts": len(result.contexts),
        },
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return AgentGenerateOut(cases=result.cases, contexts=result.contexts)


@router.get(
    "/{project_id}/functional-cases/export",
    dependencies=[Depends(require_any_permission("case.read", "ai.read"))],
)
def export_cases(project: Project = Depends(get_tenant_project), db: Session = Depends(get_db)) -> JSONResponse:
    rows = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.project_id == project.id)
        .order_by(FunctionalCase.id.asc())
        .all()
    )
    payload = {
        "project_id": project.id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "cases": [case_to_export_dict(row) for row in rows],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="cases-project-{project.id}.json"'},
        media_type="application/json",
    )


@router.post(
    "/{project_id}/functional-cases/import",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_permission("case.write"))],
)
def import_cases(
    body: FunctionalCaseBatchImport,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    created: list[FunctionalCase] = []
    for item in body.cases:
        row = create_case_row(db, project.id, item.model_dump())
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    log_action(
        db,
        module="cases",
        action="cases.imported",
        message=f"imported {len(created)} cases for project #{project.id}",
        detail={"project_id": project.id, "count": len(created)},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return created


@router.post(
    "/{project_id}/functional-cases/import-openapi",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_permission("case.write"))],
)
def import_openapi_cases(
    body: OpenApiImportIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    try:
        spec = parse_openapi_content(body.openapi_content)
        skeletons = build_case_skeletons(spec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not body.persist:
        now = datetime.now(timezone.utc)
        return [
            FunctionalCaseOut(
                id=0,
                project_id=project.id,
                title=item["title"],
                module=item.get("module"),
                preconditions=item.get("preconditions"),
                steps=item.get("steps") or [],
                expected=item.get("expected"),
                priority=item.get("priority"),
                source_requirement=item.get("source_requirement"),
                openapi_operation_id=item.get("openapi_operation_id"),
                created_at=now,
                updated_at=now,
            )
            for item in skeletons
        ]

    created: list[FunctionalCase] = []
    for item in skeletons:
        row = create_case_row(db, project.id, item)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    log_action(
        db,
        module="cases",
        action="cases.imported_openapi",
        message=f"imported {len(created)} openapi cases for project #{project.id}",
        detail={"project_id": project.id, "count": len(created)},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return created


@router.post(
    "/{project_id}/functional-cases",
    response_model=FunctionalCaseOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def create_case(
    body: FunctionalCaseCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> FunctionalCase:
    row = create_case_row(db, project.id, body.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/{project_id}/functional-cases",
    response_model=list[FunctionalCaseOut],
    dependencies=[Depends(require_any_permission("case.read", "ai.read"))],
)
def list_cases(
    suite_id: int | None = Query(default=None),
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[FunctionalCase]:
    query = db.query(FunctionalCase).filter(FunctionalCase.project_id == project.id)
    if suite_id is not None:
        from backend.services.case_service import require_suite

        suite = require_suite(db, project.id, suite_id)
        return list(suite.cases or [])
    return query.order_by(FunctionalCase.id.desc()).all()


@router.get(
    "/{project_id}/functional-cases/{case_id}",
    response_model=FunctionalCaseOut,
    dependencies=[Depends(require_any_permission("case.read", "ai.read"))],
)
def get_case(
    case_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> FunctionalCase:
    return require_case(db, project.id, case_id)


@router.patch(
    "/{project_id}/functional-cases/{case_id}",
    response_model=FunctionalCaseOut,
    dependencies=[Depends(require_permission("case.write"))],
)
def update_case(
    case_id: int,
    body: FunctionalCaseUpdate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> FunctionalCase:
    row = require_case(db, project.id, case_id)
    apply_case_update(row, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/{project_id}/functional-cases/{case_id}",
    dependencies=[Depends(require_permission("case.write"))],
)
def delete_case(
    case_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    row = require_case(db, project.id, case_id)
    db.delete(row)
    db.commit()
    return {"deleted": True, "case_id": case_id}
