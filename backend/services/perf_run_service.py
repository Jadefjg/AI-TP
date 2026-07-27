from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import AiArtifact
from backend.services.ai.constants import MODULE_PERF_PLAN
from backend.services.engines.k6_scheduler import dispatch_perf_plan_distributed
from backend.services.engines.perf_k6 import dispatch_perf_plan
from backend.core.defaults import DEFAULT_BASE_URL

PERF_MODE_LEGACY = "legacy"
PERF_MODE_K6 = "k6"
PERF_MODE_AUTO = "auto"


def _latest_perf_artifact(db: Session, project_id: int) -> AiArtifact | None:
    return (
        db.query(AiArtifact)
        .filter(
            AiArtifact.project_id == project_id,
            AiArtifact.module_type == MODULE_PERF_PLAN,
        )
        .order_by(AiArtifact.id.desc())
        .first()
    )


def should_use_k6_perf(db: Session, project_id: int, run_options: dict[str, Any] | None) -> bool:
    opts = run_options or {}
    mode = str(opts.get("perf_mode") or PERF_MODE_AUTO)
    if mode == PERF_MODE_LEGACY:
        return False
    if mode == PERF_MODE_K6:
        return True
    if opts.get("perf_artifact_id"):
        return True
    return _latest_perf_artifact(db, project_id) is not None


def execute_project_perf_k6(
    db: Session,
    project_id: int,
    run_options: dict[str, Any] | None,
) -> dict[str, Any]:
    opts = run_options or {}
    base_url = str(opts.get("perf_base_url") or DEFAULT_BASE_URL)
    artifact_id = opts.get("perf_artifact_id")
    artifact: AiArtifact | None = None
    if artifact_id:
        artifact = (
            db.query(AiArtifact)
            .filter(
                AiArtifact.id == artifact_id,
                AiArtifact.project_id == project_id,
                AiArtifact.module_type == MODULE_PERF_PLAN,
            )
            .one_or_none()
        )
    if not artifact:
        artifact = _latest_perf_artifact(db, project_id)
    if not artifact:
        return {
            "status": "skipped",
            "command_label": "k6://perf-plan",
            "exit_code": None,
            "stdout": "",
            "stderr": "无 perf_plan 产物",
            "detail": {"reason": "no perf_plan artifacts"},
        }

    plan = artifact.payload if isinstance(artifact.payload, dict) else {}
    settings = get_settings()
    distributed = bool(opts.get("perf_distributed", settings.k6_distributed_enabled))
    if distributed:
        result = dispatch_perf_plan_distributed(
            db, plan, project_id=project_id, artifact_id=artifact.id, base_url=base_url
        )
    else:
        result = dispatch_perf_plan(plan, project_id=project_id, artifact_id=artifact.id, base_url=base_url)

    status = result.get("status", "failed")
    stdout_parts: list[str] = []
    if isinstance(result.get("stdout"), str) and result.get("stdout"):
        stdout_parts.append(result["stdout"])
    for nr in result.get("node_results") or []:
        if isinstance(nr, dict) and nr.get("stdout"):
            stdout_parts.append(str(nr["stdout"]))
    return {
        "status": status,
        "command_label": f"k6://perf-plan (artifact #{artifact.id})",
        "exit_code": 0 if status == "passed" else 1,
        "stdout": "\n".join(stdout_parts)[:8000],
        "stderr": result.get("stderr") or "",
        "detail": {
            "engine": "k6",
            "job_id": result.get("job_id"),
            "summary_metrics": result.get("summary_metrics"),
            "time_series": result.get("time_series"),
            "time_series_source": (result.get("detail") or {}).get("time_series_source")
            if isinstance(result.get("detail"), dict)
            else result.get("time_series_source"),
            "execution_segments": result.get("execution_segments"),
            "mode": result.get("mode"),
        },
    }
