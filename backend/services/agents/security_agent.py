"""Security Agent — generate scan strategy via AI Gateway, execute via scanners."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import Project, SecurityScanJob
from backend.services.agents.base import AgentManifest
from backend.services.ai.constants import MODULE_SECURITY_SCAN
from backend.services.ai.scheduler import AiTaskResult, run_ai_module
from backend.services.engines.security_adapters import run_external_security_engine
from backend.services.engines.security_scanner import (
    ScanTarget,
    execute_security_scan,
    normalize_security_job_status,
)


def extract_security_strategies(payload: object) -> list:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("strategies", "items", "payload", "results", "scans"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if any(k in payload for k in ("vul_type", "test_payload", "scan_strategy")):
        return [payload]
    return []


class SecurityAgent:
    manifest = AgentManifest(
        key="security",
        label="安全 Agent",
        module_type=MODULE_SECURITY_SCAN,
        engine="builtin/nuclei/zap",
        generate="LLM → 扫描策略 / Payload",
        execute="builtin + nuclei/zap adapters",
    )

    async def generate(self, db: Session, project: Project, *, api_params: str) -> AiTaskResult:
        return await run_ai_module(
            db,
            project=project,
            module_type=MODULE_SECURITY_SCAN,
            variables={"api_params": api_params},
            use_rag=True,
        )

    def execute(
        self,
        db: Session,
        project: Project,
        *,
        artifact_id: int,
        payload: object,
        target_url: str,
        engine: str = "builtin",
        method: str = "GET",
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        body_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        strategies = extract_security_strategies(payload)
        settings = get_settings()
        target = ScanTarget(
            url=target_url,
            method=method,
            headers=headers or {},
            query_params=query_params or {},
            body_params=body_params or {},
        )
        findings: list[dict] = []
        engines_used: list[str] = []
        result: dict[str, Any] = {"status": "passed", "findings": [], "detail": {}}

        if engine in {"nuclei", "zap"}:
            ext = run_external_security_engine(engine, target_url)
            engines_used.append(engine)
            findings.extend(ext.get("findings") or [])
            result = ext
        elif engine == "combined":
            ext_n = run_external_security_engine("nuclei", target_url)
            engines_used.append("nuclei")
            findings.extend(ext_n.get("findings") or [])
            builtin = execute_security_scan(
                strategies,
                target,
                max_payloads_per_type=settings.security_scan_max_payloads,
                delay_ms=settings.security_scan_delay_ms,
            )
            engines_used.append("builtin")
            findings.extend(builtin.get("findings") or [])
            result = builtin
        else:
            result = execute_security_scan(
                strategies,
                target,
                max_payloads_per_type=settings.security_scan_max_payloads,
                delay_ms=settings.security_scan_delay_ms,
            )
            engines_used.append("builtin")
            findings = result.get("findings") or []

        status = normalize_security_job_status(result, findings)
        job = SecurityScanJob(
            project_id=project.id,
            artifact_id=artifact_id,
            target_url=target_url,
            engine=",".join(engines_used) or engine,
            status=status,
            findings=findings,
            detail={**(result.get("detail") or {}), "engines": engines_used},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        result["job_id"] = job.id
        result["agent"] = self.manifest.key
        result["findings"] = findings
        return result
