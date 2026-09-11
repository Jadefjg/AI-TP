from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_user, require_permission
from backend.api.deps import get_tenant_execution_job, get_tenant_project, get_tenant_run
from backend.db.session import get_db
from backend.models.entities import ExecutionJob, Project, TestRun, User
from backend.schemas.dto import ExecutionJobOut, RunCreate, RunOut, RunTaskOut
from backend.services.job_queue import (
    cancel_run_job,
    enqueue_test_run_job,
    list_dead_letter_jobs,
    requeue_dead_letter_job,
    retry_run_job,
)
from backend.services.orchestrator import ALLOWED_KINDS, create_run_with_items
from backend.services.audit_service import log_action
from backend.services.plan_run_service import resolve_functional_case_ids
from backend.services.tenant_service import filter_projects_for_user, is_platform_user
from backend.services.project_base_url import resolve_project_base_url

router = APIRouter(tags=["runs"])

_API_MODES = {"auto", "dsl", "pytest"}
_PERF_MODES = {"auto", "k6", "legacy"}
_SECURITY_MODES = {"auto", "ai", "legacy", "combined"}
_SECURITY_ENGINES = {"builtin", "nuclei", "zap"}


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
        next_retry_at=job.next_retry_at,
        backoff_seconds=job.backoff_seconds,
        dead_lettered_at=job.dead_lettered_at,
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
    invalid_modes = (
        ("api_mode", body.api_mode, _API_MODES),
        ("perf_mode", body.perf_mode, _PERF_MODES),
        ("security_mode", body.security_mode, _SECURITY_MODES),
        ("security_engine", body.security_engine, _SECURITY_ENGINES),
    )
    for name, value, allowed in invalid_modes:
        if value not in allowed:
            raise HTTPException(status_code=400, detail=f"invalid {name}: {value}")

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
    # Resolve omitted execution targets from the project configuration.  The
    # request model deliberately keeps these fields optional so API/CI callers
    # do not accidentally target the local development default.
    project_base_url = resolve_project_base_url(project)
    run_options = {
        "suite_id": body.suite_id,
        "plan_id": body.plan_id,
        "functional_case_ids": functional_case_ids,
        "api_base_url": body.api_base_url or project_base_url,
        "api_mode": body.api_mode,
        "regression_set_id": body.regression_set_id,
        "api_artifact_ids": body.api_artifact_ids,
        "perf_base_url": body.perf_base_url or project_base_url,
        "perf_mode": body.perf_mode,
        "perf_artifact_id": body.perf_artifact_id,
        "perf_distributed": body.perf_distributed,
        "security_mode": body.security_mode,
        "security_target_url": body.security_target_url or f"{project_base_url}/system/health",
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
        wanted = status.strip()
        if wanted == "skipped":
            # Run-level status stays "completed" when every item was skipped.
            runs_all = q.order_by(TestRun.id.desc()).limit(limit * 5).all()
            runs = [
                r
                for r in runs_all
                if (r.items or [])
                and all(i.status == "skipped" for i in (r.items or []))
                and not any(i.status in {"failed", "error"} for i in (r.items or []))
            ][:limit]
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
                        failed_item_count=0,
                        skipped_item_count=len(items),
                        item_count=len(items),
                    )
                )
            return out
        q = q.filter(TestRun.status == wanted)
    runs = q.order_by(TestRun.id.desc()).limit(limit * 3 if failed_first else limit).all()
    if failed_first:
        priority = {"failed": 0, "running": 1, "pending": 2, "cancelled": 3, "completed": 4}

        def _rank(r: TestRun) -> tuple[int, int]:
            items = r.items or []
            all_skip = (
                bool(items)
                and all(i.status == "skipped" for i in items)
                and not any(i.status in {"failed", "error"} for i in items)
            )
            if all_skip:
                return (3, -r.id)  # after cancelled-ish, before plain completed
            return (priority.get(r.status, 9), -r.id)

        runs.sort(key=_rank)
        runs = runs[:limit]
    else:
        runs = runs[:limit]
    out: list[RunTaskOut] = []
    for run in runs:
        items = run.items or []
        failed_n = sum(1 for i in items if i.status in {"failed", "error"})
        skipped_n = sum(1 for i in items if i.status == "skipped")
        out.append(
            RunTaskOut(
                id=run.id,
                project_id=run.project_id,
                project_name=run.project.name if run.project else None,
                status=run.status,
                created_at=run.created_at,
                completed_at=run.completed_at,
                kinds=[i.kind for i in items],
                failed_item_count=failed_n,
                skipped_item_count=skipped_n,
                item_count=len(items),
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
        status = 404 if str(e) in {"execution job not found", "run not found"} else 409
        raise HTTPException(status_code=status, detail=str(e)) from e
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
        status = 404 if str(e) in {"execution job not found", "run not found"} else 409
        raise HTTPException(status_code=status, detail=str(e)) from e
    return _job_out(job)  # type: ignore[return-value]


@router.get("/jobs/dead-letter", response_model=list[ExecutionJobOut], dependencies=[Depends(require_permission("run.read"))])
def dead_letter_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExecutionJobOut]:
    jobs = list_dead_letter_jobs(db)
    if is_platform_user(user):
        return [_job_out(job) for job in jobs]  # type: ignore[misc]
    allowed = {row[0] for row in filter_projects_for_user(db.query(Project.id), user).all()}
    return [_job_out(job) for job in jobs if job.run and job.run.project_id in allowed]  # type: ignore[misc]


@router.post("/jobs/{job_id}/dead-letter/requeue", response_model=ExecutionJobOut, dependencies=[Depends(require_permission("run.execute"))])
def requeue_dead_letter(job_id: int, db: Session = Depends(get_db)) -> ExecutionJobOut:
    try:
        return _job_out(requeue_dead_letter_job(db, job_id))  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
