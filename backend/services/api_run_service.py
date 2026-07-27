from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import AiArtifact, ApiRegressionSet
from backend.services.ai.constants import MODULE_API_AUTOMATION
from backend.services.engines.api_automation import execute_dsl_script
from backend.core.defaults import DEFAULT_BASE_URL

API_MODE_PYTEST = "pytest"
API_MODE_DSL = "dsl"
API_MODE_AUTO = "auto"


def _script_from_artifact(artifact: AiArtifact) -> str:
    payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    return str(payload.get("script_content") or "")


def resolve_api_scripts(
    db: Session,
    project_id: int,
    *,
    artifact_ids: list[int] | None = None,
    regression_set_id: int | None = None,
    case_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    explicit_artifact_ids = list(artifact_ids or [])
    resolved_case_ids = list(case_ids or [])

    if regression_set_id is not None:
        reg = (
            db.query(ApiRegressionSet)
            .filter(ApiRegressionSet.id == regression_set_id, ApiRegressionSet.project_id == project_id)
            .one_or_none()
        )
        if not reg:
            raise ValueError("regression set not found")
        resolved_case_ids = list(reg.case_ids or [])

    resolved: list[dict[str, Any]] = []
    seen: set[int] = set()

    for aid in explicit_artifact_ids:
        row = (
            db.query(AiArtifact)
            .filter(
                AiArtifact.id == aid,
                AiArtifact.project_id == project_id,
                AiArtifact.module_type == MODULE_API_AUTOMATION,
            )
            .one_or_none()
        )
        if row and row.id not in seen:
            seen.add(row.id)
            resolved.append(
                {
                    "artifact_id": row.id,
                    "case_id": row.case_id,
                    "title": row.title,
                    "script": _script_from_artifact(row),
                }
            )

    for cid in resolved_case_ids:
        row = (
            db.query(AiArtifact)
            .filter(
                AiArtifact.project_id == project_id,
                AiArtifact.module_type == MODULE_API_AUTOMATION,
                AiArtifact.case_id == cid,
            )
            .order_by(AiArtifact.id.desc())
            .first()
        )
        if row and row.id not in seen:
            seen.add(row.id)
            resolved.append(
                {
                    "artifact_id": row.id,
                    "case_id": row.case_id,
                    "title": row.title,
                    "script": _script_from_artifact(row),
                }
            )

    if not explicit_artifact_ids and not resolved_case_ids:
        rows = (
            db.query(AiArtifact)
            .filter(
                AiArtifact.project_id == project_id,
                AiArtifact.module_type == MODULE_API_AUTOMATION,
            )
            .order_by(AiArtifact.id.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "artifact_id": row.id,
                "case_id": row.case_id,
                "title": row.title,
                "script": _script_from_artifact(row),
            }
            for row in rows
        ]

    if regression_set_id is not None and not resolved:
        raise ValueError("回归集中绑定的用例尚无 api_automation 产物，请先生成 DSL 脚本")

    return resolved


def regression_base_url(db: Session, project_id: int, regression_set_id: int | None) -> str | None:
    if regression_set_id is None:
        return None
    reg = (
        db.query(ApiRegressionSet)
        .filter(ApiRegressionSet.id == regression_set_id, ApiRegressionSet.project_id == project_id)
        .one_or_none()
    )
    return reg.base_url if reg else None


def should_use_dsl_api(db: Session, project_id: int, run_options: dict[str, Any] | None) -> bool:
    opts = run_options or {}
    mode = str(opts.get("api_mode") or API_MODE_AUTO)
    if mode == API_MODE_PYTEST:
        return False
    if mode == API_MODE_DSL:
        return True
    if opts.get("regression_set_id") or opts.get("api_artifact_ids"):
        return True
    count = (
        db.query(AiArtifact)
        .filter(
            AiArtifact.project_id == project_id,
            AiArtifact.module_type == MODULE_API_AUTOMATION,
        )
        .count()
    )
    return count > 0


def execute_project_api_dsl(
    db: Session,
    project_id: int,
    run_options: dict[str, Any] | None,
) -> dict[str, Any]:
    opts = run_options or {}
    base_url = str(opts.get("api_base_url") or DEFAULT_BASE_URL)
    reg_url = regression_base_url(db, project_id, opts.get("regression_set_id"))
    if reg_url:
        base_url = reg_url

    try:
        scripts = resolve_api_scripts(
            db,
            project_id,
            artifact_ids=opts.get("api_artifact_ids"),
            regression_set_id=opts.get("regression_set_id"),
            case_ids=opts.get("api_case_ids"),
        )
    except ValueError as exc:
        return {
            "status": "skipped",
            "command_label": "dsl://api-automation",
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "detail": {"reason": str(exc)},
        }

    if not scripts:
        return {
            "status": "skipped",
            "command_label": "dsl://api-automation",
            "exit_code": None,
            "stdout": "",
            "stderr": "项目暂无 api_automation DSL 产物",
            "detail": {"reason": "no api_automation artifacts"},
        }

    lines: list[str] = []
    artifact_results: list[dict[str, Any]] = []
    all_ok = True

    for entry in scripts:
        script = entry["script"]
        if not script.strip():
            all_ok = False
            artifact_results.append(
                {
                    "artifact_id": entry["artifact_id"],
                    "case_id": entry["case_id"],
                    "status": "skipped",
                    "reason": "empty script_content",
                }
            )
            continue
        result = execute_dsl_script(script, base_url=base_url)
        ok = result.get("status") == "passed"
        if not ok:
            all_ok = False
        artifact_results.append(
            {
                "artifact_id": entry["artifact_id"],
                "case_id": entry["case_id"],
                "title": entry.get("title"),
                "status": result.get("status"),
                "steps": result.get("steps"),
                "stdout": result.get("stdout"),
            }
        )
        lines.append(
            f"=== artifact #{entry['artifact_id']} case={entry.get('case_id')} -> {result.get('status')} ==="
        )
        lines.append(result.get("stdout") or "")

    status = "passed" if all_ok else "failed"
    return {
        "status": status,
        "command_label": f"dsl://api-automation ({len(scripts)} scripts)",
        "exit_code": 0 if all_ok else 1,
        "stdout": "\n".join(lines)[-8000:],
        "stderr": "" if all_ok else "部分 DSL 脚本执行失败",
        "detail": {
            "engine": "dsl",
            "base_url": base_url,
            "script_count": len(scripts),
            "artifacts": artifact_results,
        },
    }
