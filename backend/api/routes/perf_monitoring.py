from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.models.entities import K6DispatchJob, Project
from backend.schemas.dto import K6DispatchJobOut, PerfMonitorOut
from backend.services.perf_bottleneck_analyzer import analyze_perf_bottleneck

router = APIRouter(prefix="/projects", tags=["perf-monitoring"])


@router.get(
    "/{project_id}/perf/k6-jobs",
    response_model=list[K6DispatchJobOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_project_k6_jobs(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[K6DispatchJob]:
    return (
        db.query(K6DispatchJob)
        .filter(K6DispatchJob.project_id == project.id)
        .order_by(K6DispatchJob.id.desc())
        .limit(30)
        .all()
    )


@router.get(
    "/{project_id}/perf/k6-jobs/{job_id}/monitor",
    response_model=PerfMonitorOut,
    dependencies=[Depends(require_permission("ai.read"))],
)
def get_k6_monitor(
    job_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    job = (
        db.query(K6DispatchJob)
        .filter(K6DispatchJob.id == job_id, K6DispatchJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="k6 job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "summary_metrics": job.summary_metrics or {},
        "time_series": job.time_series or [],
        "time_series_source": (
            (job.node_results[0].get("time_series_source") if isinstance(job.node_results, list) and job.node_results else None)
            or ((job.summary_metrics or {}).get("time_series_source") if isinstance(job.summary_metrics, dict) else None)
            or ("k6_ndjson" if job.time_series else "synthetic_from_summary")
        ),
        "execution_segments": job.execution_segments or [],
        "bottleneck_analysis": job.bottleneck_analysis,
    }


@router.post(
    "/{project_id}/perf/k6-jobs/{job_id}/analyze-bottleneck",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def analyze_k6_bottleneck(
    job_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    job = (
        db.query(K6DispatchJob)
        .filter(K6DispatchJob.id == job_id, K6DispatchJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="k6 job not found")
    result = await analyze_perf_bottleneck(db, project=project, job=job)
    job.bottleneck_analysis = result.get("analysis")
    db.commit()
    return result
