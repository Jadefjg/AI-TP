from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import AiArtifact, FunctionalCase, Project, RequirementReview
from backend.services.ai.call_logger import log_ai_call
from backend.services.ai.constants import (
    AI_MODULES,
    MODULE_API_AUTOMATION,
    MODULE_FUNCTIONAL_CASES,
    MODULE_MODEL_PROFILE,
    MODULE_OPENAPI_SPEC,
    MODULE_PERF_PLAN,
    MODULE_REQUIREMENT_REVIEW,
    MODULE_SECURITY_SCAN,
)
from backend.services.ai.context_cache import append_context, set_context
from backend.services.ai.json_utils import parse_json_payload, parse_requirement_review_response
from backend.api.request_context import get_current_user_optional
from backend.services.ai.gateway import complete as chat_completion
from backend.services.ai.llm_client import LlmResult
from backend.core.config import get_settings
from backend.services.ai.stubs import _functional_cases_stub
from backend.services.credential_service import get_project_llm_override
from backend.services.requirement_analyzer import analyze_requirement_heuristic, normalize_requirement_review_payload
from backend.services.tenant_service import assert_ai_token_quota, get_organization
from backend.services.ai.prompt_service import resolve_prompt_content
from backend.services.rag_service import retrieve_context_chunks_async


@dataclass
class AiTaskResult:
    module_type: str
    model: str
    payload: Any
    prompt_template_id: int | None
    persisted_ids: list[int]
    contexts: list[dict] | None = None
    used_fallback: bool = False


async def run_ai_module(
    db: Session,
    *,
    project: Project,
    module_type: str,
    variables: dict[str, str],
    persist: bool = True,
    use_rag: bool = False,
    requirement_snapshot: str | None = None,
    review_source_filename: str | None = None,
    review_source_format: str | None = None,
) -> AiTaskResult:
    if module_type not in AI_MODULES:
        raise ValueError(f"unsupported module_type: {module_type}")

    merged_vars = dict(variables)
    if use_rag:
        query = ""
        if "req_content" in merged_vars:
            query = merged_vars["req_content"]
        elif module_type == MODULE_API_AUTOMATION:
            query = "\n".join(
                part for part in (merged_vars.get("case_info", ""), merged_vars.get("api_info", "")) if part
            )
        elif module_type == MODULE_OPENAPI_SPEC:
            query = "\n".join(
                part
                for part in (merged_vars.get("project_context", ""), merged_vars.get("code_signals", ""))
                if part
            )
        elif module_type == MODULE_PERF_PLAN:
            query = "\n".join(
                part for part in (merged_vars.get("biz_desc", ""), merged_vars.get("api_doc", "")) if part
            )
        elif module_type == MODULE_SECURITY_SCAN:
            query = merged_vars.get("api_params", "")
        if query:
            chunks = await retrieve_context_chunks_async(db, project_id=project.id, query=query)
            if chunks:
                rag_text = "\n\n".join(c.content for c in chunks[:5])
                if "req_content" in merged_vars:
                    merged_vars["req_content"] = f"{merged_vars['req_content']}\n\n【知识库向量检索】\n{rag_text}"
                elif "api_info" in merged_vars:
                    merged_vars["api_info"] = f"{merged_vars['api_info']}\n\n【知识库向量检索】\n{rag_text}"
                elif "project_context" in merged_vars:
                    merged_vars["project_context"] = (
                        f"{merged_vars['project_context']}\n\n【知识库向量检索】\n{rag_text}"
                    )
                elif "biz_desc" in merged_vars:
                    merged_vars["biz_desc"] = f"{merged_vars['biz_desc']}\n\n【知识库向量检索】\n{rag_text}"
                elif "api_params" in merged_vars:
                    merged_vars["api_params"] = f"{merged_vars['api_params']}\n\n【知识库向量检索】\n{rag_text}"
    prompt_text, template_id = resolve_prompt_content(db, module_type, merged_vars)
    profile = MODULE_MODEL_PROFILE[module_type]
    json_mode = module_type not in {MODULE_FUNCTIONAL_CASES, MODULE_SECURITY_SCAN}

    org = get_organization(db, project.organization_id)
    assert_ai_token_quota(db, org)
    llm_override = get_project_llm_override(db, project)
    user = get_current_user_optional()
    requirement_text = requirement_snapshot or merged_vars.get("user_input_requirement", "")

    system_prompt = "你是企业级 AI 测试平台助手。严格遵守用户提示词中的输出格式约束。"
    if module_type == MODULE_REQUIREMENT_REVIEW and "【Agent 分析任务】" in prompt_text:
        system_prompt = (
            "你是企业级 AI 测试 Agent，专注产品需求评审。"
            "结合需求正文与项目知识库参考，识别歧义、逻辑缺口、可测性问题与业务风险。"
            "严格按用户提示中的 JSON 结构输出，禁止 markdown 与多余解释。"
        )
    llm: LlmResult | None = None
    payload: Any = None
    fallback_used = False
    error_detail: str | None = None
    req_content = merged_vars.get("req_content", "")
    stub_requirement = (
        requirement_text
        if module_type == MODULE_REQUIREMENT_REVIEW
        else req_content or requirement_snapshot or ""
    )
    try:
        llm = await chat_completion(
            system_prompt=system_prompt,
            user_prompt=prompt_text,
            profile=profile,
            json_mode=json_mode,
            llm_override=llm_override,
            module_type=module_type,
            requirement_text=stub_requirement or None,
        )
        used_heuristic_fallback = False
        if module_type == MODULE_REQUIREMENT_REVIEW:
            offline = llm.model in {"local-analyzer", "stub-local"}
            try:
                payload = parse_requirement_review_response(llm.content)
            except ValueError:
                payload = analyze_requirement_heuristic(requirement_text)
                used_heuristic_fallback = True
            payload = normalize_requirement_review_payload(
                payload,
                requirement_text,
                offline_only=offline or used_heuristic_fallback,
            )
        else:
            try:
                payload = parse_json_payload(llm.content)
            except ValueError:
                if module_type == MODULE_FUNCTIONAL_CASES and get_settings().ai_stub_on_failure:
                    payload = _functional_cases_stub(
                        prompt_text,
                        requirement_text=req_content,
                    )
                    llm = LlmResult(
                        content="",
                        model=f"{llm.model}-parse-fallback",
                        prompt_tokens=llm.prompt_tokens,
                        completion_tokens=llm.completion_tokens,
                        latency_ms=llm.latency_ms,
                        used_fallback=True,
                    )
                else:
                    raise
            if module_type == MODULE_OPENAPI_SPEC and isinstance(payload, dict):
                if "openapi_document" in payload and isinstance(payload["openapi_document"], dict):
                    payload = payload["openapi_document"]
                elif "paths" not in payload and isinstance(payload.get("openapi"), dict):
                    payload = payload["openapi"]
        log_ai_call(
            db,
            project_id=project.id,
            organization_id=project.organization_id,
            user_id=user.id if user else None,
            module_type=module_type,
            model_name=llm.model,
            prompt_tokens=llm.prompt_tokens,
            completion_tokens=llm.completion_tokens,
            latency_ms=llm.latency_ms,
            status="success",
            used_fallback=llm.used_fallback,
            prompt_template_id=template_id,
        )
    except Exception as exc:  # noqa: BLE001
        error_detail = str(exc)
        log_ai_call(
            db,
            project_id=project.id,
            organization_id=project.organization_id,
            user_id=user.id if user else None,
            module_type=module_type,
            model_name="n/a",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            status="failed",
            error_detail=error_detail,
            prompt_template_id=template_id,
        )
        if get_settings().ai_stub_on_failure:
            from backend.services.ai.json_utils import parse_json_payload
            from backend.services.ai.stubs import build_stub_payload

            if module_type == MODULE_FUNCTIONAL_CASES:
                payload = _functional_cases_stub(prompt_text, requirement_text=req_content)
            else:
                stub_content = build_stub_payload(
                    system_prompt=prompt_text,
                    user_prompt=prompt_text,
                    profile=MODULE_MODEL_PROFILE.get(module_type, "bulk"),
                    module_type=module_type,
                    requirement_text=req_content or requirement_text or None,
                )
                payload = parse_json_payload(stub_content)
            llm = LlmResult(
                content="",
                model="stub-local-fallback",
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0,
                used_fallback=True,
            )
            fallback_used = True
        else:
            raise

    assert llm is not None
    if fallback_used:
        log_ai_call(
            db,
            project_id=project.id,
            organization_id=project.organization_id,
            user_id=user.id if user else None,
            module_type=module_type,
            model_name=llm.model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            status="success",
            used_fallback=True,
            prompt_template_id=template_id,
        )
    persisted: list[int] = []
    contexts: list[dict] | None = None

    if module_type == MODULE_REQUIREMENT_REVIEW and persist:
        req_text = requirement_text
        review = RequirementReview(
            project_id=project.id,
            requirement_text=req_text[:50000],
            result_json=payload if isinstance(payload, dict) else {"raw": payload},
            model_name=llm.model,
            prompt_template_id=template_id,
            source_filename=review_source_filename,
            source_format=review_source_format,
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        persisted.append(review.id)

    elif module_type == MODULE_FUNCTIONAL_CASES and persist:
        cases = payload if isinstance(payload, list) else payload.get("cases", []) if isinstance(payload, dict) else []
        req_text = merged_vars.get("req_content", "")
        set_context(project.id, module_type, req_text[:20000])
        created_rows: list[FunctionalCase] = []
        for item in cases:
            if not isinstance(item, dict):
                continue
            steps_raw = item.get("operate_step") or item.get("steps") or ""
            if isinstance(steps_raw, list):
                steps = [str(s) for s in steps_raw]
            else:
                steps = [s.strip() for s in str(steps_raw).split(";") if s.strip()] or [str(steps_raw)]
            row = FunctionalCase(
                project_id=project.id,
                title=str(item.get("case_name") or item.get("title") or "未命名用例")[:512],
                preconditions=item.get("precondition") or item.get("preconditions"),
                steps=steps,
                expected=item.get("expect_result") or item.get("expected"),
                priority=str(item.get("priority") or "medium")[:32],
                module=str(item.get("module") or "")[:128] or None,
                source_requirement=req_text[:20000],
            )
            db.add(row)
            created_rows.append(row)
        db.commit()
        for row in created_rows:
            db.refresh(row)
        persisted = [r.id for r in created_rows]
        if persisted:
            from backend.services.case_service import append_cases_to_suite, ensure_pipeline_suite

            suite = ensure_pipeline_suite(db, project.id)
            append_cases_to_suite(db, suite, persisted)
            db.commit()

    elif module_type in {
        MODULE_API_AUTOMATION,
        MODULE_PERF_PLAN,
        MODULE_SECURITY_SCAN,
        MODULE_OPENAPI_SPEC,
    } and persist:
        title_map = {
            MODULE_API_AUTOMATION: "接口自动化脚本",
            MODULE_PERF_PLAN: "性能压测方案",
            MODULE_SECURITY_SCAN: "安全扫描策略",
            MODULE_OPENAPI_SPEC: "OpenAPI / Swagger 文档",
        }
        stored_payload = payload
        if module_type == MODULE_OPENAPI_SPEC and isinstance(payload, dict) and "paths" in payload:
            from backend.services.openapi_discovery import wrap_openapi_artifact_payload

            stored_payload = wrap_openapi_artifact_payload(
                payload,
                source="ai",
                remark="AI 生成的 OpenAPI 文档",
            )
        artifact = AiArtifact(
            project_id=project.id,
            module_type=module_type,
            title=title_map[module_type],
            payload=stored_payload if isinstance(stored_payload, (dict, list)) else {"raw": stored_payload},
            model_name=llm.model,
            prompt_template_id=template_id,
            case_id=int(merged_vars["case_id"]) if merged_vars.get("case_id", "").isdigit() else None,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        persisted.append(artifact.id)
        if module_type == MODULE_OPENAPI_SPEC:
            payload = stored_payload

    if module_type == MODULE_FUNCTIONAL_CASES:
        append_context(project.id, module_type, merged_vars.get("req_content", "")[:4000])

    return AiTaskResult(
        module_type=module_type,
        model=llm.model,
        payload=payload,
        prompt_template_id=template_id,
        persisted_ids=persisted,
        contexts=contexts,
        used_fallback=bool(llm.used_fallback or fallback_used),
    )
