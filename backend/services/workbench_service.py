from __future__ import annotations

import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.request_context import get_current_user_optional
from backend.models.entities import (
    AiWorkbenchMessage,
    AiWorkbenchSession,
    FunctionalCase,
    Project,
    RequirementReview,
)
from backend.services.ai.constants import AI_MODULES, MODULE_FUNCTIONAL_CASES, MODULE_REQUIREMENT_REVIEW
from backend.services.ai.llm_client import chat_completion
from backend.services.ai.scheduler import run_ai_module
from backend.services.rag_service import retrieve_context_chunks_async
from backend.services.tenant_service import assert_ai_token_quota, get_organization


def _extract_json_block(text: str) -> dict | list | None:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    raw = fenced.group(1).strip() if fenced else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def create_session(
    db: Session,
    *,
    project: Project,
    module_type: str,
    title: str | None = None,
) -> AiWorkbenchSession:
    if module_type not in AI_MODULES:
        raise HTTPException(status_code=400, detail=f"unsupported module_type: {module_type}")
    user = get_current_user_optional()
    row = AiWorkbenchSession(
        project_id=project.id,
        organization_id=project.organization_id,
        user_id=user.id if user else None,
        module_type=module_type,
        title=(title or f"{module_type} 会话")[:255],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


async def chat_in_session(
    db: Session,
    *,
    session: AiWorkbenchSession,
    project: Project,
    user_message: str,
    use_rag: bool = True,
    variables: dict[str, str] | None = None,
) -> tuple[AiWorkbenchMessage, AiWorkbenchMessage]:
    org = get_organization(db, project.organization_id)
    assert_ai_token_quota(db, org)

    rag_refs: list[dict] = []
    merged_vars = dict(variables or {})
    if use_rag:
        chunks = await retrieve_context_chunks_async(db, project_id=project.id, query=user_message)
        if chunks:
            rag_refs = [
                {"id": c.id, "title": c.title, "source": c.source, "score": getattr(c, "score", None)}
                for c in chunks[:5]
            ]
            rag_text = "\n\n".join(c.content for c in chunks[:5])
            merged_vars["rag_context"] = rag_text

    history = (
        db.query(AiWorkbenchMessage)
        .filter(AiWorkbenchMessage.session_id == session.id)
        .order_by(AiWorkbenchMessage.id.asc())
        .limit(20)
        .all()
    )
    transcript = "\n".join(f"{m.role}: {m.content[:2000]}" for m in history)

    system = (
        f"你是 AI 测试工作台助手，当前模块：{session.module_type}。"
        "结合对话历史与知识库回答；若用户需要结构化产出，在回复末尾附 ```json ... ``` 代码块。"
    )
    user_prompt = (
        f"【对话历史】\n{transcript}\n\n"
        f"【知识库片段】\n{merged_vars.get('rag_context', '（无）')}\n\n"
        f"【用户】\n{user_message}"
    )

    user_row = AiWorkbenchMessage(session_id=session.id, role="user", content=user_message, rag_refs=rag_refs or None)
    db.add(user_row)
    db.flush()

    llm = await chat_completion(
        system_prompt=system,
        user_prompt=user_prompt,
        profile="bulk_local",
        json_mode=False,
    )
    payload = _extract_json_block(llm.content)
    assistant_row = AiWorkbenchMessage(
        session_id=session.id,
        role="assistant",
        content=llm.content,
        rag_refs=rag_refs or None,
        payload=payload if isinstance(payload, (dict, list)) else None,
    )
    db.add(assistant_row)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)
    return user_row, assistant_row


async def apply_session_result(db: Session, *, session: AiWorkbenchSession, project: Project) -> dict:
    last = (
        db.query(AiWorkbenchMessage)
        .filter(AiWorkbenchMessage.session_id == session.id, AiWorkbenchMessage.role == "assistant")
        .order_by(AiWorkbenchMessage.id.desc())
        .first()
    )
    if not last:
        raise HTTPException(status_code=400, detail="no assistant message to apply")

    payload = last.payload
    if payload is None:
        payload = _extract_json_block(last.content)
    if payload is None:
        raise HTTPException(status_code=400, detail="assistant output has no JSON payload to apply")

    if session.module_type == MODULE_FUNCTIONAL_CASES:
        return await _apply_functional_cases(db, project=project, payload=payload)
    if session.module_type == MODULE_REQUIREMENT_REVIEW:
        return _apply_requirement_review(db, project=project, payload=payload, text=last.content)

    result = await run_ai_module(
        db,
        project=project,
        module_type=session.module_type,
        variables={"raw_payload": json.dumps(payload, ensure_ascii=False)[:8000]},
        persist=True,
        use_rag=False,
    )
    return {"applied": True, "module_type": session.module_type, "persisted_ids": result.persisted_ids}


async def _apply_functional_cases(db: Session, *, project: Project, payload: dict | list) -> dict:
    cases = payload if isinstance(payload, list) else payload.get("cases", []) if isinstance(payload, dict) else []
    created: list[int] = []
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
        )
        db.add(row)
        db.flush()
        created.append(row.id)
    db.commit()
    return {"applied": True, "module_type": MODULE_FUNCTIONAL_CASES, "case_ids": created, "count": len(created)}


def _apply_requirement_review(db: Session, *, project: Project, payload: dict | list, text: str) -> dict:
    review = RequirementReview(
        project_id=project.id,
        requirement_text=text[:50000],
        result_json=payload if isinstance(payload, dict) else {"raw": payload},
        model_name="workbench",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return {"applied": True, "module_type": MODULE_REQUIREMENT_REVIEW, "review_id": review.id}
