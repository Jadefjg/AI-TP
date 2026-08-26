"""Requirement Agent — review requirements via AI Gateway, land as functional cases."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import Project, RequirementReview
from backend.services.agents.base import AgentManifest
from backend.services.agent_workflow import (
    CaseGenerationWorkflow,
    RequirementReviewWorkflow,
    RequirementReviewWorkflowResult,
    WorkflowResult,
)
from backend.services.ai.constants import MODULE_FUNCTIONAL_CASES, MODULE_REQUIREMENT_REVIEW
from backend.services.ai.scheduler import AiTaskResult, run_ai_module
from backend.services.requirement_review_service import convert_review_to_cases


class RequirementAgent:
    manifest = AgentManifest(
        key="requirement",
        label="需求 Agent",
        module_type=MODULE_REQUIREMENT_REVIEW,
        engine="review+cases",
        generate="LLM → 需求评审 / 功能用例",
        execute="评审项转用例",
    )

    async def review(
        self,
        db: Session,
        project: Project,
        *,
        requirement_text: str,
        source_filename: str | None = None,
        source_format: str | None = None,
    ) -> RequirementReviewWorkflowResult:
        return await RequirementReviewWorkflow().run(
            db,
            project=project,
            requirement_text=requirement_text,
            source_filename=source_filename,
            source_format=source_format,
        )

    async def generate_cases(self, db: Session, project: Project, requirement_text: str) -> WorkflowResult:
        return await CaseGenerationWorkflow().run(db, project, requirement_text)

    async def generate_case_artifact(
        self,
        db: Session,
        project: Project,
        *,
        requirement_text: str,
        openapi_content: str | None = None,
    ) -> AiTaskResult:
        return await run_ai_module(
            db,
            project=project,
            module_type=MODULE_FUNCTIONAL_CASES,
            variables={
                "req_content": requirement_text,
                "openapi_content": openapi_content or "（未提供 OpenAPI 文档）",
            },
            use_rag=True,
        )

    def convert_to_cases(
        self,
        db: Session,
        review: RequirementReview,
        *,
        sections: list[str] | None = None,
    ) -> tuple[list, int | None]:
        return convert_review_to_cases(db, review, sections=sections)

    def execute(self, *args: Any, **kwargs: Any):
        return self.convert_to_cases(*args, **kwargs)
