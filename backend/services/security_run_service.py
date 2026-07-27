from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import AiArtifact, SecurityScanJob
from backend.services.ai.constants import MODULE_SECURITY_SCAN
from backend.services.engines.security_adapters import run_external_security_engine
from backend.services.engines.security_scanner import ScanTarget, execute_security_scan, normalize_security_job_status

SEC_MODE_LEGACY = "legacy"
SEC_MODE_AI = "ai"
SEC_MODE_COMBINED = "combined"
SEC_MODE_AUTO = "auto"


def _latest_security_artifact(db: Session, project_id: int) -> AiArtifact | None:
    return (
        db.query(AiArtifact)
        .filter(
            AiArtifact.project_id == project_id,
            AiArtifact.module_type == MODULE_SECURITY_SCAN,
        )
        .order_by(AiArtifact.id.desc())
        .first()
    )


def _strategies_from_artifact(artifact: AiArtifact) -> list[dict[str, Any]]:
    payload = artifact.payload
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("strategies") or payload.get("items") or []
    return []


def should_integrate_ai_security(db: Session, project_id: int, run_options: dict[str, Any] | None) -> bool:
    opts = run_options or {}
    mode = str(opts.get("security_mode") or SEC_MODE_AUTO)
    if mode == SEC_MODE_LEGACY:
        return False
    if mode in {SEC_MODE_AI, SEC_MODE_COMBINED}:
        return True
    if opts.get("security_artifact_id") or opts.get("security_target_url"):
        return True
    return _latest_security_artifact(db, project_id) is not None


def execute_legacy_security_command(cmd: str, cwd: str, timeout_sec: int) -> dict[str, Any]:
    if not Path(cwd).is_dir():
        return {"status": "skipped", "stdout": "", "stderr": "", "exit_code": None, "detail": {"reason": f"code_root 不存在: {cwd}"}}
    try:
        proc = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {"status": "error", "stdout": "", "stderr": "timeout", "exit_code": None, "detail": {"reason": "执行超时"}}
    if proc.returncode == 127 or "command not found" in (proc.stderr or "").lower():
        return {
            "status": "skipped",
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "exit_code": proc.returncode,
            "detail": {"reason": "测试工具未安装或不在 PATH"},
        }
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-8000:],
        "exit_code": proc.returncode,
        "detail": {"engine": "legacy"},
    }


def execute_integrated_security(
    db: Session,
    project_id: int,
    *,
    kind: str,
    run_id: int | None,
    run_options: dict[str, Any] | None,
    legacy_cmd: str,
    cwd: str,
) -> dict[str, Any]:
    opts = run_options or {}
    settings = get_settings()
    mode = str(opts.get("security_mode") or SEC_MODE_AUTO)
    target_url = str(opts.get("security_target_url") or "http://127.0.0.1:8002/system/health")
    external_engine = str(opts.get("security_engine") or "builtin")

    legacy_result: dict[str, Any] | None = None
    if mode in {SEC_MODE_LEGACY, SEC_MODE_COMBINED, SEC_MODE_AUTO}:
        legacy_result = execute_legacy_security_command(legacy_cmd, cwd, settings.default_test_timeout_sec)

    ai_result: dict[str, Any] | None = None
    job_id: int | None = None
    if mode in {SEC_MODE_AI, SEC_MODE_COMBINED, SEC_MODE_AUTO} and should_integrate_ai_security(db, project_id, opts):
        artifact_id = opts.get("security_artifact_id")
        artifact = None
        if artifact_id:
            artifact = (
                db.query(AiArtifact)
                .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project_id)
                .one_or_none()
            )
        if not artifact:
            artifact = _latest_security_artifact(db, project_id)

        findings: list[dict[str, Any]] = []
        engines_used: list[str] = []
        if external_engine in {"nuclei", "zap"}:
            ext = run_external_security_engine(external_engine, target_url)
            engines_used.append(external_engine)
            findings.extend(ext.get("findings") or [])
            ai_result = ext
        elif artifact:
            strategies = _strategies_from_artifact(artifact)
            builtin = execute_security_scan(
                strategies,
                ScanTarget(url=target_url),
                max_payloads_per_type=settings.security_scan_max_payloads,
                delay_ms=settings.security_scan_delay_ms,
            )
            engines_used.append("builtin")
            findings.extend(builtin.get("findings") or [])
            ai_result = builtin

        if findings or artifact or external_engine in {"nuclei", "zap"}:
            job_status = normalize_security_job_status(ai_result or {}, findings)
            job = SecurityScanJob(
                project_id=project_id,
                artifact_id=artifact.id if artifact else None,
                run_id=run_id,
                target_url=target_url,
                engine=",".join(engines_used) or "builtin",
                status=job_status,
                findings=findings,
                detail={"kind": kind, "engines": engines_used, "integrated_run": True, **((ai_result or {}).get("detail") or {})},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = job.id
            ai_result = ai_result or {"status": job.status, "findings": findings}

    parts = []
    if legacy_result:
        parts.append(f"[legacy/{kind}] {legacy_result.get('status')}")
    if ai_result:
        parts.append(f"[ai] findings={len(ai_result.get('findings') or [])} job=#{job_id}")

    overall = "passed"
    if legacy_result and legacy_result.get("status") == "failed":
        overall = "failed"
    # Findings = risks reported; mark run failed for gate, but job itself is completed.
    if ai_result and (ai_result.get("findings") or []):
        overall = "failed"
    if ai_result and str(ai_result.get("status") or "") == "skipped" and not (ai_result.get("findings") or []):
        if not legacy_result or legacy_result.get("status") == "skipped":
            overall = "skipped"
    if legacy_result and legacy_result.get("status") == "skipped" and not ai_result:
        overall = "skipped"

    return {
        "status": overall,
        "command_label": f"security://integrated ({kind})",
        "exit_code": 0 if overall == "passed" else 1,
        "stdout": "\n".join(parts),
        "stderr": legacy_result.get("stderr", "") if legacy_result else "",
        "detail": {
            "legacy": legacy_result,
            "ai": ai_result,
            "security_job_id": job_id,
            "kind": kind,
        },
    }
