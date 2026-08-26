"""UI Agent — generate Playwright DSL, execute via GUI Agent engine."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import Project
from backend.services.agents.base import AgentManifest
from backend.services.case_service import require_case
from backend.services.engines.ui_playwright import (
    dispatch_or_execute_ui_agent,
    execute_ui_step,
    list_ui_steps,
    steps_from_functional_case,
    steps_to_playwright_code,
)


class UiAgent:
    manifest = AgentManifest(
        key="ui",
        label="UI Agent",
        module_type="ui_automation",
        engine="playwright",
        generate="functional case → Playwright DSL",
        execute="GUI Agent (Chromium observe + act)",
    )

    def generate(self, db: Session, project: Project, *, case_id: int) -> dict[str, Any]:
        row = require_case(db, project.id, case_id)
        doc = steps_from_functional_case(row, force_rebuild=True)
        if not doc.get("steps"):
            raise ValueError("当前用例没有可转换的步骤，请先完善功能用例")
        row.ui_script = doc
        db.commit()
        return {
            "case_id": row.id,
            "ui_script": doc,
            "playwright_code": steps_to_playwright_code(doc),
            "agent": self.manifest.key,
        }

    def preview(self, ui_script: dict | list, *, base_url: str) -> dict[str, Any]:
        result = list_ui_steps(ui_script, base_url=base_url)
        result["agent"] = self.manifest.key
        return result

    def execute_step(self, ui_script: dict | list, step_index: int, *, base_url: str) -> dict[str, Any]:
        result = execute_ui_step(ui_script, step_index, base_url=base_url)
        result["agent"] = self.manifest.key
        return result

    def execute(self, ui_script: dict | list, *, base_url: str) -> dict[str, Any]:
        result = dispatch_or_execute_ui_agent(ui_script, base_url=base_url)
        result["agent"] = self.manifest.key
        return result
