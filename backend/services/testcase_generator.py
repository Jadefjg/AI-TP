from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import FunctionalCase, Project
from backend.services.ai.constants import MODULE_FUNCTIONAL_CASES
from backend.services.ai.scheduler import run_ai_module


async def generate_and_persist(
    db: Session,
    project: Project,
    requirement_text: str,
    context_chunks: list[str] | None = None,
    openapi_content: str = "",
) -> list[FunctionalCase]:
    openapi = openapi_content or "（未提供 OpenAPI 文档）"
    if context_chunks:
        rag = "\n\n".join(context_chunks[:5])
        openapi = f"{openapi}\n\n【知识库参考】\n{rag}"

    result = await run_ai_module(
        db,
        project=project,
        module_type=MODULE_FUNCTIONAL_CASES,
        variables={"req_content": requirement_text, "openapi_content": openapi},
        persist=True,
        use_rag=not context_chunks,
    )
    if not result.persisted_ids:
        return []
    return (
        db.query(FunctionalCase)
        .filter(FunctionalCase.id.in_(result.persisted_ids))
        .order_by(FunctionalCase.id.asc())
        .all()
    )


async def _generate_by_llm(requirement: str, context_chunks: list[str] | None = None) -> list[dict[str, Any]]:
    """Backward-compatible helper for legacy callers."""
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        project = db.query(Project).first()
        if not project:
            return []
        rows = await generate_and_persist(db, project, requirement, context_chunks)
        return [
            {
                "title": row.title,
                "preconditions": row.preconditions,
                "steps": row.steps,
                "expected": row.expected,
                "priority": row.priority,
            }
            for row in rows
        ]
    finally:
        db.close()
