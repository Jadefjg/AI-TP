from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_user, require_permission
from backend.api.deps import get_tenant_execution_job, get_tenant_project, get_tenant_run
from backend.db.session import get_db
from backend.models.entities import ExecutionJob, Project, TestRun, User
from backend.schemas.dto import ExecutionJobOut, RunCreate, RunOut, RunTaskOut
from backend.services.job_queue import cancel_run_job, enqueue_test_run_job, retry_run_job
from backend.services.orchestrator import ALLOWED_KINDS, create_run_with_items
from backend.services.audit_service import log_action
from backend.services.plan_run_service import resolve_functional_case_ids
from backend.services.tenant_service import filter_projects_for_user, is_platform_user

router = APIRouter(tags=["runs"])


def _job_out(job: ExecutionJob | None) -> ExecutionJobOut | None:
    if not job:
        return None
    return ExecutionJobOut(
        id=job.id,
        run_id=job.run_id,
        job_type=job.job_type,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested,
        last_error=job.last_error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunOut,
    status_code=202,
    dependencies=[Depends(require_permission("run.execute"))],
)
def start_run(
    body: RunCreate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> TestRun:
    if body.suite_id is not None and body.plan_id is not None:
        raise HTTPException(status_code=400, detail="suite_id and plan_id are mutually exclusive")

    try:
        functional_case_ids = resolve_functional_case_ids(
            db,
            project_id=project.id,
            suite_id=body.suite_id,
            plan_id=body.plan_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    kinds = list(body.kinds or [])
    if functional_case_ids and "functional" not in kinds:
        kinds.append("functional")
    if not kinds:
        kinds = ["functional"] if functional_case_ids else list(ALLOWED_KINDS)

    unknown = [k for k in kinds if k not in ALLOWED_KINDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown kinds: {unknown}")

    run = create_run_with_items(db, project_id=project.id, kinds=kinds)
    run_options = {
        "suite_id": body.suite_id,
        "plan_id": body.plan_id,
        "functional_case_ids": functional_case_ids,
        "api_base_url": body.api_base_url,
        "api_mode": body.api_mode,
        "regression_set_id": body.regression_set_id,
        "api_artifact_ids": body.api_artifact_ids,
        "perf_base_url": body.perf_base_url,
        "perf_mode": body.perf_mode,
        "perf_artifact_id": body.perf_artifact_id,
        "perf_distributed": body.perf_distributed,
        "security_mode": body.security_mode,
        "security_target_url": body.security_target_url,
        "security_artifact_id": body.security_artifact_id,
        "security_engine": body.security_engine,
    }
    enqueue_test_run_job(
        db,
        run_id=run.id,
        command_overrides=body.command_overrides,
        run_options=run_options,
    )
    log_action(
        db,
        module="runs",
        action="run.queued",
        message=f"run #{run.id} queued for execution",
        detail={"run_id": run.id, "project_id": project.id, "kinds": kinds},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return (
        db.query(TestRun)
        .options(selectinload(TestRun.items), selectinload(TestRun.execution_job))
        .filter(TestRun.id == run.id)
        .one()
    )


@router.get(
    "/runs/recent",
    response_model=list[RunTaskOut],
    dependencies=[Depends(require_permission("run.read"))],
)
def list_recent_runs(
    limit: int = 30,
    status: str | None = None,
    failed_first: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RunTaskOut]:
    limit = min(max(limit, 1), 100)
    q = db.query(TestRun).options(selectinload(TestRun.items), selectinload(TestRun.project))
    if not is_platform_user(user):
        allowed = [row[0] for row in filter_projects_for_user(db.query(Project.id), user).all()]
        if not allowed:
            return []
        q = q.filter(TestRun.project_id.in_(allowed))
    if status:
        q = q.filter(TestRun.status == status.strip())
    runs = q.order_by(TestRun.id.desc()).limit(limit * 3 if failed_first else limit).all()
    if failed_first:
        priority = {"failed": 0, "running": 1, "pending": 2, "cancelled": 3, "completed": 4}
        runs.sort(key=lambda r: (priority.get(r.status, 9), -r.id))
        runs = runs[:limit]
    else:
        runs = runs[:limit]
    out: list[RunTaskOut] = []
    for run in runs:
        items = run.items or []
        out.append(
            RunTaskOut(
                id=run.id,
                project_id=run.project_id,
                project_name=run.project.name if run.project else None,
                status=run.status,
                created_at=run.created_at,
                completed_at=run.completed_at,
                kinds=[i.kind for i in items],
                failed_item_count=sum(1 for i in items if i.status in {"failed", "error"}),
            )
        )
    return out


@router.get("/runs/{run_id}", response_model=RunOut, dependencies=[Depends(require_permission("run.read"))])
def get_run(run: TestRun = Depends(get_tenant_run)) -> TestRun:
    return run


@router.get(
    "/runs/{run_id}/execution-job",
    response_model=ExecutionJobOut,
    dependencies=[Depends(require_permission("run.read"))],
)
def get_run_execution_job(job: ExecutionJob = Depends(get_tenant_execution_job)) -> ExecutionJobOut:
    return _job_out(job)  # type: ignore[return-value]


@router.post(
    "/runs/{run_id}/cancel",
    response_model=ExecutionJobOut,
    dependencies=[Depends(require_permission("run.execute"))],
)
def cancel_run(job: ExecutionJob = Depends(get_tenant_execution_job), db: Session = Depends(get_db)) -> ExecutionJobOut:
    try:
        job = cancel_run_job(db, job.run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _job_out(job)  # type: ignore[return-value]


@router.post(
    "/runs/{run_id}/retry",
    response_model=ExecutionJobOut,
    dependencies=[Depends(require_permission("run.execute"))],
)
def retry_run(job: ExecutionJob = Depends(get_tenant_execution_job), db: Session = Depends(get_db)) -> ExecutionJobOut:
    try:
        job = retry_run_job(db, job.run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _job_out(job)  # type: ignore[return-value]
