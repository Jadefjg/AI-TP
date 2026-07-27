from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.models.entities import ExecutionJob, Project, TestRun, User
from backend.services.tenant_service import get_project_for_user


def get_tenant_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    """Resolve project with tenant isolation (platform admin bypass)."""
    return get_project_for_user(db, user, project_id)


def get_tenant_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TestRun:
    """Load run and enforce tenant access via its project."""
    run = (
        db.query(TestRun)
        .options(
            selectinload(TestRun.items),
            selectinload(TestRun.execution_job),
            selectinload(TestRun.project),
        )
        .filter(TestRun.id == run_id)
        .one_or_none()
    )
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    get_project_for_user(db, user, run.project_id)
    return run


def get_tenant_execution_job(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExecutionJob:
    """Load execution job for a run with tenant check."""
    get_tenant_run(run_id, db, user)
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="execution job not found")
    return job
