"""Interface Agent — generate API DSL via AI Gateway, execute via DSL engine."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import Project
from backend.services.agents.base import AgentManifest
from backend.services.ai.constants import MODULE_API_AUTOMATION
from backend.services.ai.scheduler import AiTaskResult, run_ai_module
from backend.services.engines.api_automation import execute_dsl_script


class InterfaceAgent:
    manifest = AgentManifest(
        key="interface",
        label="接口 Agent",
        module_type=MODULE_API_AUTOMATION,
        engine="api_dsl",
        generate="LLM → YAML DSL artifact",
        execute="HTTP DSL runner",
    )

    async def generate(
        self,
        db: Session,
        project: Project,
        *,
        case_info: str,
        api_info: str,
        case_id: int | None = None,
    ) -> AiTaskResult:
        variables = {"case_info": case_info, "api_info": api_info}
        if case_id is not None:
            variables["case_id"] = str(case_id)
        return await run_ai_module(
            db,
            project=project,
            module_type=MODULE_API_AUTOMATION,
            variables=variables,
            use_rag=True,
        )

    def execute(self, script: str, *, base_url: str) -> dict[str, Any]:
        result = execute_dsl_script(script, base_url=base_url)
        result["agent"] = self.manifest.key
        return result
