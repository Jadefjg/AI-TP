from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models.entities import FunctionalCase, Project
from backend.services.ai.constants import MODULE_FUNCTIONAL_CASES, MODULE_REQUIREMENT_REVIEW
from backend.services.ai.scheduler import AiTaskResult, run_ai_module
from backend.services.requirement_analyzer import (
    merge_review_payloads,
    normalize_requirement_review_payload,
    split_requirement_sections,
)
from backend.services.requirement_review_service import persist_requirement_review
from backend.services.rag_service import retrieve_context_chunks_async

CHUNK_THRESHOLD = 12000
CHUNK_SIZE = 8000


@dataclass
class WorkflowResult:
    cases: list[FunctionalCase]
    contexts: list[dict]


@dataclass
class RequirementReviewWorkflowResult:
    task: AiTaskResult
    contexts: list[dict]
    mode: str


def _context_meta(chunks) -> list[dict]:
    return [
        {
            "id": c.id,
            "source": c.source,
            "title": c.title,
            "content_preview": c.content[:220] + ("..." if len(c.content) > 220 else ""),
        }
        for c in chunks
    ]


def _build_agent_requirement_prompt(requirement_text: str, rag_text: str) -> str:
    sections = [
        "【Agent 分析任务】",
        "你正在以 AI Agent 模式评审以下产品需求文档。",
        "请结合正文与项目知识库参考（若有），从需求歧义、逻辑缺失、可测性缺陷、业务风险四个维度输出结构化 JSON。",
        "每条问题必须引用文档中的具体位置或原文片段，给出风险等级(高/中/低)与可执行整改建议。",
        "JSON 字段：ambiguity_list、miss_logic_list、untestable_list、biz_risk_list。",
        "",
        "【待评审需求正文】",
        requirement_text.strip(),
    ]
    if rag_text:
        sections.extend(["", "【项目知识库参考（向量检索）】", rag_text])
    else:
        sections.extend(["", "【项目知识库参考】", "（未命中相关知识条目）"])
    return "\n".join(sections)


class RequirementReviewWorkflow:
    """
    Agent workflow: RAG retrieve -> enrich prompt -> LLM requirement review -> persist review.
    Long documents are analyzed in segments and merged.
    """

    async def run(
        self,
        db: Session,
        project: Project,
        requirement_text: str,
        *,
        source_filename: str | None = None,
        source_format: str | None = None,
    ) -> RequirementReviewWorkflowResult:
        text = (requirement_text or "").strip()
        if len(text) < 10:
            raise ValueError("需求正文过短，至少需要 10 个字符")

        rag_chunks = await retrieve_context_chunks_async(db, project_id=project.id, query=text)
        context_meta = _context_meta(rag_chunks)
        rag_text = "\n\n".join(c.content for c in rag_chunks[:5]) if rag_chunks else ""

        if len(text) <= CHUNK_THRESHOLD:
            task = await self._analyze_once(
                db,
                project=project,
                agent_prompt=_build_agent_requirement_prompt(text, rag_text),
                requirement_snapshot=text,
                source_filename=source_filename,
                source_format=source_format,
            )
            mode = "agent+rag" if rag_chunks else "agent"
            return RequirementReviewWorkflowResult(task=task, contexts=context_meta, mode=mode)

        sections = split_requirement_sections(text, CHUNK_SIZE)
        partial_payloads: list[dict] = []
        model_name = ""
        template_id: int | None = None
        for idx, section in enumerate(sections, 1):
            section_prompt = _build_agent_requirement_prompt(
                f"【文档分段 {idx}/{len(sections)}】\n{section}",
                rag_text if idx == 1 else "",
            )
            partial = await self._analyze_once(
                db,
                project=project,
                agent_prompt=section_prompt,
                requirement_snapshot=section,
                source_filename=None,
                source_format=None,
                persist=False,
            )
            model_name = partial.model
            template_id = partial.prompt_template_id
            if isinstance(partial.payload, dict):
                partial_payloads.append(partial.payload)

        merged = merge_review_payloads(*partial_payloads)
        offline = model_name in {"local-analyzer", "stub-local"}
        merged = normalize_requirement_review_payload(merged, text, offline_only=offline)
        review = persist_requirement_review(
            db,
            project_id=project.id,
            requirement_text=text,
            result_json=merged,
            model_name=model_name,
            prompt_template_id=template_id,
            source_filename=source_filename,
            source_format=source_format,
        )
        task = AiTaskResult(
            module_type=MODULE_REQUIREMENT_REVIEW,
            model=model_name,
            payload=merged,
            prompt_template_id=template_id,
            persisted_ids=[review.id],
            used_fallback=offline or "fallback" in str(model_name).lower() or "stub" in str(model_name).lower(),
        )
        mode = f"agent+chunked({len(sections)})" + ("+rag" if rag_chunks else "")
        return RequirementReviewWorkflowResult(task=task, contexts=context_meta, mode=mode)

    async def _analyze_once(
        self,
        db: Session,
        *,
        project: Project,
        agent_prompt: str,
        requirement_snapshot: str,
        source_filename: str | None,
        source_format: str | None,
        persist: bool = True,
    ) -> AiTaskResult:
        return await run_ai_module(
            db,
            project=project,
            module_type=MODULE_REQUIREMENT_REVIEW,
            variables={"user_input_requirement": agent_prompt},
            requirement_snapshot=requirement_snapshot,
            review_source_filename=source_filename,
            review_source_format=source_format,
            persist=persist,
        )


class CaseGenerationWorkflow:
    """
    Agent workflow: RAG retrieve -> AI scheduler (prompt template) -> persist cases.
    """

    async def run(self, db: Session, project: Project, requirement_text: str) -> WorkflowResult:
        chunks = await retrieve_context_chunks_async(db, project_id=project.id, query=requirement_text)
        context_meta = _context_meta(chunks)
        rag_text = "\n\n".join(c.content for c in chunks[:5]) if chunks else ""
        openapi = f"（Agent 模式）\n{rag_text}" if rag_text else "（Agent 模式，无知识库命中）"
        result = await run_ai_module(
            db,
            project=project,
            module_type=MODULE_FUNCTIONAL_CASES,
            variables={"req_content": requirement_text, "openapi_content": openapi},
            persist=True,
            use_rag=bool(chunks),
        )
        cases = (
            db.query(FunctionalCase)
            .filter(FunctionalCase.id.in_(result.persisted_ids))
            .order_by(FunctionalCase.id.asc())
            .all()
            if result.persisted_ids
            else []
        )
        return WorkflowResult(cases=cases, contexts=context_meta)
