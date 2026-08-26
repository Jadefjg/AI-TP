"""Performance Agent — generate k6 plan via AI Gateway, execute via k6 engine."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import K6DispatchJob, Project
from backend.services.agents.base import AgentManifest
from backend.services.ai.constants import MODULE_PERF_PLAN
from backend.services.ai.scheduler import AiTaskResult, run_ai_module
from backend.services.engines.k6_scheduler import dispatch_perf_plan_distributed
from backend.services.engines.perf_k6 import dispatch_perf_plan


class PerfAgent:
    manifest = AgentManifest(
        key="perf",
        label="性能 Agent",
        module_type=MODULE_PERF_PLAN,
        engine="k6",
        generate="LLM → k6 压测方案",
        execute="k6 local / distributed",
    )

    async def generate(
        self,
        db: Session,
        project: Project,
        *,
        biz_desc: str,
        api_doc: str,
    ) -> AiTaskResult:
        return await run_ai_module(
            db,
            project=project,
            module_type=MODULE_PERF_PLAN,
            variables={"biz_desc": biz_desc, "api_doc": api_doc},
            use_rag=True,
        )

    def execute(
        self,
        db: Session,
        project: Project,
        *,
        artifact_id: int,
        plan: dict[str, Any],
        base_url: str,
        distributed: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        if distributed and settings.k6_distributed_enabled:
            capped = dict(plan)
            capped["duration"] = min(int(capped.get("duration") or 15), 15)
            capped["warmup"] = min(int(capped.get("warmup") or 0), 3)
            result = dispatch_perf_plan_distributed(
                db, capped, project_id=project.id, artifact_id=artifact_id, base_url=base_url
            )
        else:
            result = dispatch_perf_plan(
                plan,
                project_id=project.id,
                artifact_id=artifact_id,
                base_url=base_url,
                interactive=True,
            )
            status = str(result.get("status") or "failed")
            job_status = (
                "completed" if status == "passed" else ("skipped" if status == "skipped" else "failed")
            )
            job = K6DispatchJob(
                project_id=project.id,
                artifact_id=artifact_id,
                status=job_status,
                plan_snapshot=plan if isinstance(plan, dict) else {},
                node_results=[
                    {
                        "mode": "local-direct",
                        **{k: v for k, v in result.items() if k != "generated_script_preview"},
                    }
                ],
                master_script_path=str(result.get("script_path") or ""),
                summary_metrics=result.get("summary_metrics"),
                time_series=result.get("time_series") or [],
                execution_segments=[],
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            result = {**result, "job_id": job.id, "mode": "local-direct"}
        result["agent"] = self.manifest.key
        return result
