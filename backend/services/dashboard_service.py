from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.entities import (
    AiCallLog,
    AuditLog,
    FunctionalCase,
    K6DispatchJob,
    Project,
    RunStatus,
    TestRun,
    TestRunItem,
)
from backend.schemas.dto import (
    DashboardK6Snapshot,
    DashboardRunTrendPoint,
    DashboardRunTrendsOut,
    DashboardSummaryOut,
)


@dataclass(frozen=True)
class DashboardScope:
    """None organization_id = platform-wide (admin only)."""

    organization_id: int | None


def _project_ids_query(db: Session, scope: DashboardScope):
    q = db.query(Project.id)
    if scope.organization_id is not None:
        q = q.filter(Project.organization_id == scope.organization_id)
    return q


def _run_query(db: Session, scope: DashboardScope):
    q = db.query(TestRun)
    if scope.organization_id is not None:
        q = q.filter(TestRun.project_id.in_(_project_ids_query(db, scope)))
    return q


def build_dashboard_summary(db: Session, *, scope: DashboardScope) -> DashboardSummaryOut:
    project_q = db.query(func.count(Project.id))
    if scope.organization_id is not None:
        project_q = project_q.filter(Project.organization_id == scope.organization_id)
    project_count = project_q.scalar() or 0

    case_q = db.query(func.count(FunctionalCase.id))
    if scope.organization_id is not None:
        case_q = case_q.join(Project, FunctionalCase.project_id == Project.id).filter(
            Project.organization_id == scope.organization_id
        )
    case_count = case_q.scalar() or 0

    audit_q = db.query(func.count(AuditLog.id)).filter(
        AuditLog.module == "cases",
        AuditLog.action.in_(("cases.generated", "cases.generated_agent")),
    )
    if scope.organization_id is not None:
        audit_q = audit_q.filter(AuditLog.organization_id == scope.organization_id)
    case_generation_count = audit_q.scalar() or 0

    def _count_runs(*filters) -> int:
        q = _run_query(db, scope)
        for clause in filters:
            q = q.filter(clause)
        return q.with_entities(func.count(TestRun.id)).scalar() or 0

    total_run_count = _count_runs()
    failed_run_count = _count_runs(TestRun.status == RunStatus.failed.value)
    running_run_count = _count_runs(TestRun.status == RunStatus.running.value)
    pending_run_count = _count_runs(TestRun.status == RunStatus.pending.value)
    latest_run = _run_query(db, scope).order_by(TestRun.id.desc()).first()

    def _count_kinds(kinds: tuple[str, ...]) -> int:
        item_q = db.query(func.count(TestRunItem.id)).filter(TestRunItem.kind.in_(kinds))
        if scope.organization_id is not None:
            item_q = item_q.join(TestRun, TestRunItem.run_id == TestRun.id).filter(
                TestRun.project_id.in_(_project_ids_query(db, scope))
            )
        return item_q.scalar() or 0

    ai_q = db.query(func.count(AiCallLog.id))
    prompt_q = db.query(func.coalesce(func.sum(AiCallLog.prompt_tokens), 0))
    completion_q = db.query(func.coalesce(func.sum(AiCallLog.completion_tokens), 0))
    if scope.organization_id is not None:
        ai_q = ai_q.filter(AiCallLog.organization_id == scope.organization_id)
        prompt_q = prompt_q.filter(AiCallLog.organization_id == scope.organization_id)
        completion_q = completion_q.filter(AiCallLog.organization_id == scope.organization_id)
    ai_call_count = ai_q.scalar() or 0
    prompt_tokens = prompt_q.scalar() or 0
    completion_tokens = completion_q.scalar() or 0

    k6_q = db.query(K6DispatchJob)
    if scope.organization_id is not None:
        k6_q = k6_q.filter(K6DispatchJob.project_id.in_(_project_ids_query(db, scope)))
    latest_k6_job = k6_q.order_by(K6DispatchJob.id.desc()).first()
    latest_k6 = None
    if latest_k6_job:
        k6_project = db.query(Project).filter(Project.id == latest_k6_job.project_id).one_or_none()
        detail = latest_k6_job.node_results if isinstance(latest_k6_job.node_results, list) else []
        source = "synthetic_from_summary"
        if detail and isinstance(detail[0], dict):
            source = str(detail[0].get("time_series_source") or source)
        latest_k6 = DashboardK6Snapshot(
            job_id=latest_k6_job.id,
            project_id=latest_k6_job.project_id,
            project_name=k6_project.name if k6_project else None,
            status=latest_k6_job.status,
            summary_metrics=latest_k6_job.summary_metrics or {},
            time_series=latest_k6_job.time_series or [],
            time_series_source=source,
        )

    return DashboardSummaryOut(
        organization_id=scope.organization_id,
        project_count=project_count,
        case_count=case_count,
        case_generation_count=case_generation_count,
        unit_run_count=_count_kinds(("unit",)),
        functional_run_count=_count_kinds(("functional",)),
        automation_run_count=_count_kinds(("api", "ui")),
        performance_run_count=_count_kinds(("perf_backend", "perf_frontend")),
        security_run_count=_count_kinds(("sec_backend", "sec_frontend")),
        total_run_count=total_run_count,
        latest_run_status=latest_run.status if latest_run else None,
        ai_call_count=ai_call_count,
        ai_token_total=int(prompt_tokens) + int(completion_tokens),
        failed_run_count=failed_run_count,
        running_run_count=running_run_count,
        pending_run_count=pending_run_count,
        latest_k6=latest_k6,
    )


def build_run_trends(db: Session, *, scope: DashboardScope, days: int) -> DashboardRunTrendsOut:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)
    run_q = _run_query(db, scope).filter(TestRun.created_at >= start)
    runs = run_q.with_entities(TestRun.status, TestRun.created_at).all()

    buckets: dict[str, dict[str, int]] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        buckets[day] = {"total": 0, "failed": 0, "completed": 0}

    for status, created_at in runs:
        if not created_at:
            continue
        day_key = created_at.astimezone(timezone.utc).date().isoformat()
        if day_key not in buckets:
            continue
        buckets[day_key]["total"] += 1
        if status == RunStatus.failed.value:
            buckets[day_key]["failed"] += 1
        elif status == RunStatus.completed.value:
            buckets[day_key]["completed"] += 1

    points = [
        DashboardRunTrendPoint(date=day, total=v["total"], failed=v["failed"], completed=v["completed"])
        for day, v in sorted(buckets.items())
    ]
    return DashboardRunTrendsOut(organization_id=scope.organization_id, days=days, points=points)
