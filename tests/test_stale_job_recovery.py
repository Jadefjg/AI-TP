"""Stale / orphaned execution job recovery."""

from datetime import datetime, timedelta, timezone

from backend.db.session import SessionLocal
from backend.models.entities import ExecutionJob, JobStatus, RunStatus, TestRun, TestRunItem
from backend.services.job_queue import job_is_stale, recover_stale_execution_jobs


def test_recover_stale_running_job(monkeypatch):
    monkeypatch.setenv("JOB_WORKER_IN_API", "true")
    monkeypatch.setenv("JOB_QUEUE_BACKEND", "db")
    from backend.core.config import get_settings

    get_settings.cache_clear()

    db = SessionLocal()
    try:
        run = TestRun(project_id=1, status=RunStatus.running.value)
        db.add(run)
        db.commit()
        db.refresh(run)
        item = TestRunItem(run_id=run.id, kind="perf_backend", status="running")
        db.add(item)
        job = ExecutionJob(
            job_type="test_run",
            run_id=run.id,
            status=JobStatus.running.value,
            payload={},
            attempt_count=1,
            max_attempts=3,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(job)
        db.commit()
        run_id, job_id = run.id, job.id

        recovered = recover_stale_execution_jobs(db)
        assert recovered >= 1

        db.expire_all()
        run2 = db.query(TestRun).filter(TestRun.id == run_id).one()
        job2 = db.query(ExecutionJob).filter(ExecutionJob.id == job_id).one()
        item2 = db.query(TestRunItem).filter(TestRunItem.run_id == run_id).one()
        assert run2.status == RunStatus.failed.value
        assert run2.completed_at is not None
        assert job2.status == JobStatus.failed.value
        assert item2.status == "error"
    finally:
        db.close()
        get_settings.cache_clear()


def test_job_is_stale_by_age():
    job = ExecutionJob(
        job_type="test_run",
        run_id=1,
        status=JobStatus.running.value,
        payload={},
        started_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    assert job_is_stale(job, max_age_sec=60) is True
    job.started_at = datetime.now(timezone.utc)
    assert job_is_stale(job, max_age_sec=3600) is False
