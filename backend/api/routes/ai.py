from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_permission
from backend.api.deps import get_tenant_project
from backend.db.session import get_db
from backend.core.config import get_settings
from backend.core.defaults import DEFAULT_BASE_URL
from backend.models.entities import (
    AiArtifact,
    AiAsyncJob,
    AiCallLog,
    Project,
    PromptFeedback,
    PromptTemplate,
    RequirementReview,
    SecurityScanJob,
    User,
)
from backend.schemas.dto import (
    AiArtifactOut,
    AiAsyncJobEnqueueIn,
    AiAsyncJobOut,
    AiTaskOut,
    AiUsageSummaryOut,
    ApiArtifactScriptUpdate,
    ApiAutomationAiIn,
    ApiFailureAnalyzeIn,
    DslExecuteIn,
    FunctionalCasesAiIn,
    LlmStatusOut,
    OpenApiSpecAiIn,
    PerfDispatchIn,
    SecurityFindingReviewIn,
    SecurityScanExecuteIn,
    SecurityScanJobOut,
    PerfPlanAiIn,
    PromptFeedbackIn,
    PromptFeedbackOut,
    PromptOptimizationOut,
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplateUpdate,
    RequirementDocumentParseOut,
    RequirementReviewDiffOut,
    RequirementReviewIn,
    RequirementReviewOut,
    RequirementReviewUrlIn,
    ReviewConvertCasesIn,
    ReviewConvertCasesOut,
    SecurityScanAiIn,
)
from backend.services.ai.constants import (
    MODULE_API_AUTOMATION,
    MODULE_FUNCTIONAL_CASES,
    MODULE_OPENAPI_SPEC,
    MODULE_PERF_PLAN,
    MODULE_REQUIREMENT_REVIEW,
    MODULE_SECURITY_SCAN,
)
from backend.services.ai.prompt_optimizer import (
    apply_suggestions_to_template,
    build_optimization_suggestions,
    record_feedback,
)
from backend.services.ai.prompt_service import (
    bump_template_version,
    delete_prompt_template,
    list_module_types,
    seed_builtin_templates,
)
from backend.services.agents import (
    interface_agent,
    list_agent_manifests,
    perf_agent,
    requirement_agent,
    security_agent,
)
from backend.services.agents.metrics import agent_quality_stats
from backend.services.ai.gateway import gateway_stats
from backend.services.ai.scheduler import run_ai_module
from backend.services.ai_job_queue import QUEUEABLE_MODULES, enqueue_ai_job
from backend.services.audit_service import log_action
from backend.services.api_failure_analyzer import analyze_api_failure
from backend.services.security_report import build_security_scan_html, build_security_scan_pdf
from backend.services.ai.prompt_optimizer import record_feedback
from backend.services.openapi_discovery import (
    build_openapi_from_signals,
    discover_project_openapi,
    fetch_openapi_from_url,
    format_signals_for_prompt,
    parse_openapi_text,
    wrap_openapi_artifact_payload,
)
from backend.services.project_base_url import resolve_project_base_url
from backend.services.requirement_document import fetch_requirement_from_url, parse_requirement_document
from backend.services.requirement_pdf import build_requirement_review_pdf
from backend.services.requirement_report import build_requirement_review_html
from backend.services.requirement_review_service import diff_requirement_reviews
from backend.services.tenant_service import get_project_for_user

router = APIRouter(tags=["ai"])


def _project_api_context(project: Project) -> str:
    source = (project.repo_source or "local").strip().lower() or "local"
    lines = [
        f"项目名称: {project.name}",
        f"项目来源: {source}",
        f"代码路径/仓库/访问地址: {project.code_root}",
    ]
    if project.repo_branch:
        lines.append(f"默认分支: {project.repo_branch}")
    if project.description:
        lines.append(f"项目描述: {project.description}")
    sut = resolve_project_base_url(project)
    lines.append(f"默认被测 Base URL: {sut}")
    if source == "deployed":
        lines.append(f"部署 Base URL: {project.code_root}")
        lines.append("说明: 项目已部署上线，请围绕可访问的服务地址设计接口自动化 DSL。")
    elif source == "remote":
        lines.append("说明: 远程 Git 仓库项目，请结合业务上下文推断主要 HTTP 接口并输出 DSL。")
    else:
        lines.append("说明: 本地代码仓库项目，请结合业务上下文推断主要 HTTP 接口并输出 DSL。")
    return "\n".join(lines)


def _to_task_out(result, *, contexts: list[dict] | None = None) -> AiTaskOut:
    return AiTaskOut(
        module_type=result.module_type,
        model=result.model,
        payload=result.payload,
        prompt_template_id=result.prompt_template_id,
        persisted_ids=result.persisted_ids,
        contexts=contexts if contexts is not None else result.contexts,
        used_fallback=bool(getattr(result, "used_fallback", False) or "-fallback" in str(result.model)),
    )


def _to_requirement_agent_out(workflow_result) -> AiTaskOut:
    return _to_task_out(workflow_result.task, contexts=workflow_result.contexts)


async def _run_requirement_review_agent(
    db: Session,
    *,
    project: Project,
    requirement_text: str,
    source_filename: str | None = None,
    source_format: str | None = None,
    action: str,
    message: str,
    detail: dict | None = None,
) -> AiTaskOut:
    try:
        workflow_result = await requirement_agent.review(
            db,
            project,
            requirement_text=requirement_text,
            source_filename=source_filename,
            source_format=source_format,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_action(
        db,
        module="ai",
        action=action,
        message=message,
        detail={
            **(detail or {}),
            "mode": workflow_result.mode,
            "contexts": len(workflow_result.contexts),
            "review_id": workflow_result.task.persisted_ids[0] if workflow_result.task.persisted_ids else None,
        },
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return _to_requirement_agent_out(workflow_result)


@router.get("/ai/modules", response_model=list[str], dependencies=[Depends(require_permission("ai.read"))])
def list_ai_modules() -> list[str]:
    return list_module_types()


@router.get("/ai/agents", dependencies=[Depends(require_permission("ai.read"))])
def list_test_agents(db: Session = Depends(get_db)) -> dict:
    """Access-layer catalog of specialized test Agents."""
    return {
        "agents": [
            {
                "key": item.key,
                "label": item.label,
                "module_type": item.module_type,
                "engine": item.engine,
                "generate": item.generate,
                "execute": item.execute,
                "layer": item.layer,
            }
            for item in list_agent_manifests()
        ],
        "gateway": gateway_stats(),
        "quality": agent_quality_stats(db),
    }


@router.get("/ai/pipeline-status", dependencies=[Depends(require_permission("ai.read"))])
def ai_pipeline_status() -> dict:
    """LLM + per-agent tool readiness for the five pipeline Agents."""
    from backend.services.agents.readiness import pipeline_status_payload

    return pipeline_status_payload()


def _build_ai_job_request(payload: AiAsyncJobEnqueueIn) -> dict:
    module = payload.module_type.strip()
    if module not in QUEUEABLE_MODULES:
        raise HTTPException(status_code=400, detail=f"unsupported module_type: {module}")
    data = payload.model_dump(exclude_none=True)
    data.pop("module_type", None)
    if module == MODULE_REQUIREMENT_REVIEW and not (data.get("requirement_text") or "").strip():
        raise HTTPException(status_code=400, detail="requirement_text is required")
    if module == MODULE_FUNCTIONAL_CASES and not (data.get("requirement_text") or "").strip():
        raise HTTPException(status_code=400, detail="requirement_text is required")
    if module == MODULE_PERF_PLAN and not (data.get("biz_desc") or "").strip():
        raise HTTPException(status_code=400, detail="biz_desc is required")
    return data


@router.post(
    "/projects/{project_id}/ai/jobs",
    response_model=AiAsyncJobOut,
    status_code=202,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def enqueue_project_ai_job(
    body: AiAsyncJobEnqueueIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiAsyncJob:
    request_payload = _build_ai_job_request(body)
    try:
        job = enqueue_ai_job(
            db,
            project=project,
            module_type=body.module_type.strip(),
            request_payload=request_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_action(
        db,
        module="ai",
        action="ai_job.enqueued",
        message=f"ai job #{job.id} enqueued ({job.module_type})",
        detail={"job_id": job.id, "module_type": job.module_type},
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return job


@router.get(
    "/projects/{project_id}/ai/jobs/{job_id}",
    response_model=AiAsyncJobOut,
    dependencies=[Depends(require_permission("ai.read"))],
)
def get_project_ai_job(
    job_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiAsyncJob:
    job = (
        db.query(AiAsyncJob)
        .filter(AiAsyncJob.id == job_id, AiAsyncJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="ai job not found")
    return job


@router.get(
    "/projects/{project_id}/ai/jobs",
    response_model=list[AiAsyncJobOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_project_ai_jobs(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
    limit: int = 20,
) -> list[AiAsyncJob]:
    limit = max(1, min(limit, 100))
    return (
        db.query(AiAsyncJob)
        .filter(AiAsyncJob.project_id == project.id)
        .order_by(AiAsyncJob.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/ai/llm-status", response_model=LlmStatusOut, dependencies=[Depends(require_permission("ai.read"))])
def llm_status() -> LlmStatusOut:
    settings = get_settings()
    return LlmStatusOut(
        configured=settings.llm_configured(),
        provider=settings.resolved_llm_provider(),
        high_precision_model=settings.resolved_high_precision_model(),
        bulk_model=settings.resolved_bulk_model(),
    )


@router.get(
    "/ai/prompt-templates",
    response_model=list[PromptTemplateOut],
    dependencies=[Depends(require_permission("prompt.read"))],
)
def list_prompt_templates(
    module_type: str | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[PromptTemplate]:
    q = db.query(PromptTemplate).order_by(PromptTemplate.module_type, PromptTemplate.version.desc())
    if module_type:
        q = q.filter(PromptTemplate.module_type == module_type)
    if active_only:
        q = q.filter(PromptTemplate.is_active.is_(True))
    return q.all()


@router.post(
    "/ai/prompt-templates",
    response_model=PromptTemplateOut,
    dependencies=[Depends(require_permission("prompt.write"))],
)
def create_prompt_template(body: PromptTemplateCreate, db: Session = Depends(get_db)) -> PromptTemplate:
    if body.is_active:
        db.query(PromptTemplate).filter(
            PromptTemplate.module_type == body.module_type,
            PromptTemplate.is_active.is_(True),
        ).update({"is_active": False})
    row = PromptTemplate(
        module_type=body.module_type,
        name=body.name,
        content=body.content,
        model_profile=body.model_profile,
        version=1,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, module="ai", action="prompt.created", message=f"prompt #{row.id} created")
    return row


@router.patch(
    "/ai/prompt-templates/{template_id}",
    response_model=PromptTemplateOut,
    dependencies=[Depends(require_permission("prompt.write"))],
)
def update_prompt_template(
    template_id: int,
    body: PromptTemplateUpdate,
    db: Session = Depends(get_db),
) -> PromptTemplate:
    row = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="prompt template not found")
    if body.new_version:
        return bump_template_version(
            db,
            row,
            content=body.content,
            is_active=body.is_active if body.is_active is not None else True,
        )
    if body.name is not None:
        row.name = body.name
    if body.content is not None:
        row.content = body.content
    if body.model_profile is not None:
        row.model_profile = body.model_profile
    if body.is_active is not None:
        if body.is_active:
            db.query(PromptTemplate).filter(
                PromptTemplate.module_type == row.module_type,
                PromptTemplate.id != row.id,
                PromptTemplate.is_active.is_(True),
            ).update({"is_active": False})
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/ai/prompt-templates/{template_id}",
    dependencies=[Depends(require_permission("prompt.write"))],
)
def remove_prompt_template(template_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="prompt template not found")
    name = row.name
    module_type = row.module_type
    version = row.version
    delete_prompt_template(db, row)
    db.commit()
    log_action(
        db,
        module="ai",
        action="prompt.deleted",
        message=f"prompt {name} v{version} deleted",
        detail={"module_type": module_type, "template_id": template_id},
    )
    return {"deleted": True, "template_id": template_id}


@router.post(
    "/ai/prompt-templates/seed",
    response_model=dict,
    dependencies=[Depends(require_permission("prompt.write"))],
)
def seed_prompts(db: Session = Depends(get_db)) -> dict:
    seed_builtin_templates(db)
    return {"ok": True}


@router.get(
    "/ai/usage/summary",
    response_model=AiUsageSummaryOut,
    dependencies=[Depends(require_permission("ai.read"))],
)
def ai_usage_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AiUsageSummaryOut:
    from backend.services.ai_usage_service import build_ai_usage_summary
    from backend.services.tenant_service import is_platform_user

    org_id = None if is_platform_user(user) else user.organization_id
    return build_ai_usage_summary(db, organization_id=org_id)


@router.post(
    "/projects/{project_id}/ai/requirement-review",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_requirement_review(
    payload: RequirementReviewIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    return await _run_requirement_review_agent(
        db,
        project=project,
        requirement_text=payload.requirement_text,
        source_filename=payload.source_filename,
        source_format=payload.source_format,
        action="requirement_review.agent",
        message=f"agent review for project #{project.id}",
    )


@router.post(
    "/projects/{project_id}/ai/requirement-reviews/parse-document",
    response_model=RequirementDocumentParseOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def parse_requirement_document_upload(
    file: UploadFile = File(...),
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> RequirementDocumentParseOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        text, fmt = parse_requirement_document(filename=file.filename or "upload.txt", content=raw)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return RequirementDocumentParseOut(
        text=text,
        format=fmt,
        filename=file.filename or "upload",
        char_count=len(text),
    )


@router.post(
    "/projects/{project_id}/ai/requirement-review/upload",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_requirement_review_upload(
    file: UploadFile = File(...),
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        text, fmt = parse_requirement_document(filename=file.filename or "upload.txt", content=raw)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _run_requirement_review_agent(
        db,
        project=project,
        requirement_text=text,
        source_filename=file.filename,
        source_format=fmt,
        action="requirement_review.upload_agent",
        message=f"agent review from file for project #{project.id}",
        detail={"filename": file.filename},
    )


@router.post(
    "/projects/{project_id}/ai/requirement-review/from-url",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_requirement_review_from_url(
    body: RequirementReviewUrlIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    try:
        text, fmt, source = fetch_requirement_from_url(body.url)
    except (ValueError, RuntimeError, httpx.HTTPError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _run_requirement_review_agent(
        db,
        project=project,
        requirement_text=text,
        source_filename=source,
        source_format=fmt,
        action="requirement_review.from_url_agent",
        message=f"agent review from url for project #{project.id}",
        detail={"url": body.url},
    )


@router.get(
    "/projects/{project_id}/ai/requirement-reviews",
    response_model=list[RequirementReviewOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_requirement_reviews(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[RequirementReview]:
    return (
        db.query(RequirementReview)
        .filter(RequirementReview.project_id == project.id)
        .order_by(RequirementReview.id.desc())
        .limit(50)
        .all()
    )


@router.get(
    "/projects/{project_id}/ai/requirement-reviews/{review_id}/pdf",
    dependencies=[Depends(require_permission("ai.read"))],
)
def export_requirement_review_pdf(
    review_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> Response:
    review = (
        db.query(RequirementReview)
        .filter(RequirementReview.id == review_id, RequirementReview.project_id == project.id)
        .one_or_none()
    )
    if not review:
        raise HTTPException(status_code=404, detail="需求评审记录不存在")
    try:
        pdf_bytes = build_requirement_review_pdf(review, project_name=project.name)
    except Exception as exc:  # noqa: BLE001 - surface PDF build failures as API error
        raise HTTPException(status_code=500, detail=f"生成 PDF 失败：{exc}") from exc
    filename = f"requirement-review-{review_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/projects/{project_id}/ai/requirement-reviews/{review_id}/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_permission("ai.read"))],
)
def preview_requirement_review_html(
    review_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    review = (
        db.query(RequirementReview)
        .filter(RequirementReview.id == review_id, RequirementReview.project_id == project.id)
        .one_or_none()
    )
    if not review:
        raise HTTPException(status_code=404, detail="requirement review not found")
    html = build_requirement_review_html(review, project_name=project.name)
    return HTMLResponse(content=html)


@router.get(
    "/projects/{project_id}/ai/requirement-reviews/diff",
    response_model=RequirementReviewDiffOut,
    dependencies=[Depends(require_permission("ai.read"))],
)
def diff_requirement_review_versions(
    from_id: int,
    to_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> RequirementReviewDiffOut:
    older = (
        db.query(RequirementReview)
        .filter(RequirementReview.id == from_id, RequirementReview.project_id == project.id)
        .one_or_none()
    )
    newer = (
        db.query(RequirementReview)
        .filter(RequirementReview.id == to_id, RequirementReview.project_id == project.id)
        .one_or_none()
    )
    if not older or not newer:
        raise HTTPException(status_code=404, detail="review version not found")
    if older.id > newer.id:
        older, newer = newer, older
    data = diff_requirement_reviews(older, newer)
    return RequirementReviewDiffOut(**data)


@router.post(
    "/projects/{project_id}/ai/requirement-reviews/{review_id}/convert-to-cases",
    response_model=ReviewConvertCasesOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def convert_review_items_to_cases(
    review_id: int,
    payload: ReviewConvertCasesIn | None = None,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> ReviewConvertCasesOut:
    review = (
        db.query(RequirementReview)
        .filter(RequirementReview.id == review_id, RequirementReview.project_id == project.id)
        .one_or_none()
    )
    if not review:
        raise HTTPException(status_code=404, detail="requirement review not found")
    sections = payload.sections if payload else None
    created, suite_id = requirement_agent.convert_to_cases(db, review, sections=sections)
    log_action(
        db,
        module="ai",
        action="requirement_review.convert_cases",
        message=f"review #{review_id} -> {len(created)} cases",
    )
    return ReviewConvertCasesOut(
        review_id=review_id,
        case_ids=[c.id for c in created],
        count=len(created),
        suite_id=suite_id,
    )


@router.post(
    "/projects/{project_id}/ai/functional-cases",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_functional_cases(
    payload: FunctionalCasesAiIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    try:
        result = await requirement_agent.generate_case_artifact(
            db,
            project,
            requirement_text=payload.requirement_text,
            openapi_content=payload.openapi_content,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_task_out(result)


@router.post(
    "/projects/{project_id}/ai/api-automation",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_api_automation(
    payload: ApiAutomationAiIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    project_ctx = _project_api_context(project)
    api_info = (payload.api_info or "").strip() or "（未额外提供接口说明）"
    if project_ctx not in api_info:
        api_info = f"{project_ctx}\n\n{api_info}"
    case_info = (payload.case_info or "").strip() or (
        "基于当前项目整体能力，覆盖主流程与异常断言，生成接口自动化场景。"
    )
    try:
        result = await interface_agent.generate(
            db,
            project,
            case_info=case_info,
            api_info=api_info,
            case_id=payload.case_id,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_task_out(result)


def _persist_openapi_artifact(
    db: Session,
    *,
    project: Project,
    document: dict,
    source: str,
    remark: str,
    model_name: str,
) -> AiArtifact:
    artifact = AiArtifact(
        project_id=project.id,
        module_type=MODULE_OPENAPI_SPEC,
        title="OpenAPI / Swagger 文档",
        payload=wrap_openapi_artifact_payload(document, source=source, remark=remark),
        model_name=model_name,
        prompt_template_id=None,
        case_id=None,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


@router.post(
    "/projects/{project_id}/ai/openapi-spec",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_openapi_spec(
    payload: OpenApiSpecAiIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    mode = (payload.mode or "discover").strip().lower()
    if mode not in {"discover", "url", "manual"}:
        raise HTTPException(status_code=400, detail="mode must be discover, url or manual")

    extra = (payload.notes or "").strip()

    if mode == "manual":
        try:
            document = parse_openapi_text(payload.openapi_content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        artifact = _persist_openapi_artifact(
            db,
            project=project,
            document=document,
            source="manual",
            remark=extra or "用户手动录入的 OpenAPI / Swagger 文档",
            model_name="manual",
        )
        return AiTaskOut(
            module_type=MODULE_OPENAPI_SPEC,
            model="manual",
            payload=artifact.payload if isinstance(artifact.payload, dict) else {"raw": artifact.payload},
            prompt_template_id=None,
            persisted_ids=[artifact.id],
        )

    if mode == "url":
        try:
            document, fetched_from = fetch_openapi_from_url(payload.openapi_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        remark = f"从 URL 拉取: {fetched_from}"
        if extra:
            remark = f"{remark}；{extra}"
        artifact = _persist_openapi_artifact(
            db,
            project=project,
            document=document,
            source="url_fetch",
            remark=remark,
            model_name="url-fetch",
        )
        return AiTaskOut(
            module_type=MODULE_OPENAPI_SPEC,
            model="url-fetch",
            payload=artifact.payload if isinstance(artifact.payload, dict) else {"raw": artifact.payload},
            prompt_template_id=None,
            persisted_ids=[artifact.id],
        )

    discovery = discover_project_openapi(project)
    notes = list(discovery.notes)
    if extra:
        notes.append(f"用户补充: {extra}")

    # Prefer existing / fetched document unless caller forces AI rewrite.
    if discovery.document and not payload.force_ai:
        artifact = _persist_openapi_artifact(
            db,
            project=project,
            document=discovery.document,
            source=discovery.source,
            remark="；".join(notes) or "从项目发现的 OpenAPI 文档",
            model_name="discovery",
        )
        log_action(
            db,
            module="ai",
            action="openapi_spec.discovered",
            message=f"openapi discovered for project #{project.id}",
            detail={"artifact_id": artifact.id, "source": discovery.source},
            organization_id=project.organization_id,
            project_id=project.id,
        )
        return AiTaskOut(
            module_type=MODULE_OPENAPI_SPEC,
            model="discovery",
            payload=artifact.payload if isinstance(artifact.payload, dict) else {"raw": artifact.payload},
            prompt_template_id=None,
            persisted_ids=[artifact.id],
        )

    project_context = _project_api_context(project)
    if notes:
        project_context = f"{project_context}\n\n发现说明:\n" + "\n".join(f"- {n}" for n in notes)
    code_signals = format_signals_for_prompt(discovery.signals)
    draft = build_openapi_from_signals(
        project_name=project.name,
        signals=discovery.signals,
        server_url=discovery.server_url,
        description=project.description,
    )

    try:
        result = await run_ai_module(
            db,
            project=project,
            module_type=MODULE_OPENAPI_SPEC,
            variables={
                "project_context": project_context,
                "code_signals": code_signals,
            },
            use_rag=True,
        )
        return _to_task_out(result)
    except (ValueError, RuntimeError) as exc:
        # Deterministic fallback so DeepSeek/LLM failures still produce usable Swagger.
        artifact = _persist_openapi_artifact(
            db,
            project=project,
            document=draft,
            source="signal_fallback",
            remark=f"模型不可用，已用代码扫描结果生成。原因: {exc}",
            model_name="signal-fallback",
        )
        log_action(
            db,
            module="ai",
            action="openapi_spec.fallback",
            message=f"openapi fallback for project #{project.id}",
            detail={"artifact_id": artifact.id, "error": str(exc)},
            organization_id=project.organization_id,
            project_id=project.id,
        )
        return AiTaskOut(
            module_type=MODULE_OPENAPI_SPEC,
            model="signal-fallback",
            payload=artifact.payload if isinstance(artifact.payload, dict) else {"raw": artifact.payload},
            prompt_template_id=None,
            persisted_ids=[artifact.id],
        )


@router.post(
    "/projects/{project_id}/ai/perf-plan",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_perf_plan(
    payload: PerfPlanAiIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    project_ctx = _project_api_context(project)
    biz_desc = (payload.biz_desc or "").strip() or (
        f"基于项目「{project.name}」进行接口性能压测方案设计，覆盖主路径与关键链路。"
    )
    if project_ctx not in biz_desc:
        biz_desc = f"{project_ctx}\n\n{biz_desc}"
    api_doc = (payload.api_doc or "").strip() or "（未提供额外接口文档）"
    try:
        result = await perf_agent.generate(
            db,
            project,
            biz_desc=biz_desc,
            api_doc=api_doc,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_task_out(result)


@router.post(
    "/projects/{project_id}/ai/security-scan",
    response_model=AiTaskOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def ai_security_scan(
    payload: SecurityScanAiIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiTaskOut:
    project_ctx = _project_api_context(project)
    api_params = (payload.api_params or "").strip() or (
        f"基于项目「{project.name}」推断主要 HTTP 入参与攻击面，覆盖注入、越权、敏感信息等风险。"
    )
    if project_ctx not in api_params:
        api_params = f"{project_ctx}\n\n{api_params}"
    try:
        result = await security_agent.generate(db, project, api_params=api_params)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_task_out(result)


@router.get(
    "/projects/{project_id}/ai/artifacts",
    response_model=list[AiArtifactOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_ai_artifacts(
    module_type: str | None = None,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[AiArtifact]:
    q = db.query(AiArtifact).filter(AiArtifact.project_id == project.id)
    if module_type:
        q = q.filter(AiArtifact.module_type == module_type)
    return q.order_by(AiArtifact.id.desc()).limit(100).all()


@router.post(
    "/projects/{project_id}/ai/artifacts/{artifact_id}/execute",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def execute_api_artifact(
    artifact_id: int,
    body: DslExecuteIn | None = None,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    artifact = (
        db.query(AiArtifact)
        .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project.id)
        .one_or_none()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.module_type != MODULE_API_AUTOMATION:
        raise HTTPException(status_code=400, detail="only api_automation artifacts can be executed")
    payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    script = (body.script_content if body and body.script_content else None) or str(
        payload.get("script_content") or ""
    )
    base_url = (body.base_url if body else None) or DEFAULT_BASE_URL
    result = interface_agent.execute(script, base_url=base_url)
    log_action(
        db,
        module="engines",
        action="api_automation.execute",
        message=f"artifact #{artifact_id} dsl executed",
        detail=result,
    )
    return result


@router.patch(
    "/projects/{project_id}/ai/artifacts/{artifact_id}/script",
    response_model=AiArtifactOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def update_api_artifact_script(
    artifact_id: int,
    body: ApiArtifactScriptUpdate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> AiArtifact:
    artifact = (
        db.query(AiArtifact)
        .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project.id)
        .one_or_none()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.module_type != MODULE_API_AUTOMATION:
        raise HTTPException(status_code=400, detail="only api_automation artifacts can be edited")
    payload = dict(artifact.payload) if isinstance(artifact.payload, dict) else {}
    payload["script_content"] = body.script_content
    artifact.payload = payload
    if body.title:
        artifact.title = body.title
    db.commit()
    db.refresh(artifact)
    return artifact


@router.post(
    "/projects/{project_id}/ai/artifacts/{artifact_id}/analyze-failure",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
async def analyze_api_artifact_failure(
    artifact_id: int,
    body: ApiFailureAnalyzeIn | None = None,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    artifact = (
        db.query(AiArtifact)
        .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project.id)
        .one_or_none()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.module_type != MODULE_API_AUTOMATION:
        raise HTTPException(status_code=400, detail="only api_automation artifacts supported")
    payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    script = str(payload.get("script_content") or "")
    opts = body or ApiFailureAnalyzeIn()
    base_url = opts.base_url or DEFAULT_BASE_URL
    execution_result = opts.execution_result
    if execution_result is None or opts.rerun:
        execution_result = interface_agent.execute(script, base_url=base_url)
    if execution_result.get("status") == "passed":
        return {
            "skipped": True,
            "reason": "执行已通过，无需失败归因",
            "execution_result": execution_result,
        }
    analysis = await analyze_api_failure(
        db,
        project=project,
        artifact=artifact,
        execution_result=execution_result,
        script_content=script,
    )
    log_action(
        db,
        module="api_automation",
        action="failure.analyzed",
        message=f"artifact #{artifact_id} failure analyzed",
        detail={"model": analysis.get("model")},
    )
    return {"execution_result": execution_result, **analysis}


@router.post(
    "/projects/{project_id}/ai/artifacts/{artifact_id}/dispatch-perf",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def dispatch_perf_artifact(
    artifact_id: int,
    body: PerfDispatchIn | None = None,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    artifact = (
        db.query(AiArtifact)
        .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project.id)
        .one_or_none()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="压测产物不存在")
    if artifact.module_type != MODULE_PERF_PLAN:
        raise HTTPException(status_code=400, detail="仅压测方案产物可下发 k6")
    plan = artifact.payload if isinstance(artifact.payload, dict) else {}
    base_url = (body.base_url if body else None) or DEFAULT_BASE_URL
    use_distributed = bool(body.distributed) if body and body.distributed is not None else False
    result = perf_agent.execute(
        db,
        project,
        artifact_id=artifact_id,
        plan=plan,
        base_url=base_url,
        distributed=use_distributed,
    )
    log_action(
        db,
        module="agents",
        action="perf_agent.execute",
        message=f"artifact #{artifact_id} k6 dispatched",
        detail={"status": result.get("status")},
    )
    return result


@router.post(
    "/ai/prompt-feedback",
    response_model=PromptFeedbackOut,
    dependencies=[Depends(require_permission("prompt.write"))],
)
def create_prompt_feedback(
    body: PromptFeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PromptFeedback:
    if body.project_id is not None:
        get_project_for_user(db, user, body.project_id)
    row = record_feedback(
        db,
        project_id=body.project_id,
        module_type=body.module_type,
        source_type=body.source_type,
        source_id=body.source_id,
        original_text=body.original_text,
        corrected_text=body.corrected_text,
        prompt_template_id=body.prompt_template_id,
        note=body.note,
    )
    log_action(db, module="ai", action="prompt.feedback", message=f"feedback #{row.id} recorded")
    return row


@router.get(
    "/ai/prompt-feedback/suggestions",
    response_model=PromptOptimizationOut,
    dependencies=[Depends(require_permission("prompt.read"))],
)
def get_prompt_suggestions(module_type: str, db: Session = Depends(get_db)) -> PromptOptimizationOut:
    data = build_optimization_suggestions(db, module_type=module_type)
    return PromptOptimizationOut(**data)


@router.post(
    "/ai/prompt-templates/apply-suggestions",
    response_model=PromptTemplateOut,
    dependencies=[Depends(require_permission("prompt.write"))],
)
def apply_prompt_suggestions(module_type: str, db: Session = Depends(get_db)) -> PromptTemplate:
    try:
        row = apply_suggestions_to_template(db, module_type=module_type, mark_applied=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_action(db, module="ai", action="prompt.apply_suggestions", message=f"template v{row.version} for {module_type}")
    return row


@router.post(
    "/projects/{project_id}/ai/artifacts/{artifact_id}/dispatch-security",
    response_model=dict,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def dispatch_security_artifact(
    artifact_id: int,
    body: SecurityScanExecuteIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    artifact = (
        db.query(AiArtifact)
        .filter(AiArtifact.id == artifact_id, AiArtifact.project_id == project.id)
        .one_or_none()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.module_type != MODULE_SECURITY_SCAN:
        raise HTTPException(status_code=400, detail="only security_scan artifacts can be dispatched")

    result = security_agent.execute(
        db,
        project,
        artifact_id=artifact_id,
        payload=artifact.payload,
        target_url=body.target_url,
        engine=body.engine,
        method=body.method,
        headers=body.headers,
        query_params=body.query_params,
        body_params=body.body_params,
    )
    log_action(
        db,
        module="agents",
        action="security_agent.execute",
        message=f"artifact #{artifact_id} security scan",
        detail={"finding_count": len(result.get("findings") or [])},
    )
    return result


@router.get(
    "/projects/{project_id}/ai/security-scan-jobs",
    response_model=list[SecurityScanJobOut],
    dependencies=[Depends(require_permission("ai.read"))],
)
def list_security_scan_jobs(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> list[SecurityScanJob]:
    return (
        db.query(SecurityScanJob)
        .filter(SecurityScanJob.project_id == project.id)
        .order_by(SecurityScanJob.id.desc())
        .limit(50)
        .all()
    )


@router.get(
    "/projects/{project_id}/ai/security-scan-jobs/{job_id}/report.html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_permission("ai.read"))],
)
def security_scan_report_html(
    job_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> str:
    job = (
        db.query(SecurityScanJob)
        .filter(SecurityScanJob.id == job_id, SecurityScanJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="security scan job not found")
    return build_security_scan_html(job, project_name=project.name)


@router.get(
    "/projects/{project_id}/ai/security-scan-jobs/{job_id}/report.pdf",
    dependencies=[Depends(require_permission("ai.read"))],
)
def security_scan_report_pdf(
    job_id: int,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> Response:
    job = (
        db.query(SecurityScanJob)
        .filter(SecurityScanJob.id == job_id, SecurityScanJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="安全扫描任务不存在")
    try:
        content = build_security_scan_pdf(job, project_name=project.name)
    except Exception as exc:  # noqa: BLE001 - surface PDF build failures as API error
        raise HTTPException(status_code=500, detail=f"生成 PDF 失败：{exc}") from exc
    filename = f"security-scan-{job_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post(
    "/projects/{project_id}/ai/security-scan-jobs/{job_id}/findings/{finding_index}/review",
    response_model=SecurityScanJobOut,
    dependencies=[Depends(require_permission("ai.execute"))],
)
def review_security_finding(
    job_id: int,
    finding_index: int,
    body: SecurityFindingReviewIn,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> SecurityScanJob:
    job = (
        db.query(SecurityScanJob)
        .filter(SecurityScanJob.id == job_id, SecurityScanJob.project_id == project.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=404, detail="security scan job not found")
    findings = job.findings if isinstance(job.findings, list) else []
    if finding_index < 0 or finding_index >= len(findings):
        raise HTTPException(status_code=400, detail="finding_index out of range")

    reviews = dict(job.finding_reviews or {})
    reviews[str(finding_index)] = {"status": body.status, "note": body.note}
    job.finding_reviews = reviews

    if body.feed_prompt and body.status in {"false_positive", "confirmed"}:
        item = findings[finding_index] if isinstance(findings[finding_index], dict) else {}
        record_feedback(
            db,
            project_id=project.id,
            module_type=MODULE_SECURITY_SCAN,
            source_type="security_finding",
            source_id=job.id,
            original_text=str(item),
            corrected_text=f"[{body.status}] {body.note or ''}",
            note=f"finding #{finding_index} review",
        )

    db.commit()
    db.refresh(job)
    log_action(
        db,
        module="security_scan",
        action="finding.reviewed",
        message=f"job #{job_id} finding #{finding_index} -> {body.status}",
        detail={"job_id": job_id, "finding_index": finding_index, "status": body.status},
    )
    return job
