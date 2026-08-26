from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import AiArtifact, Project
from backend.services.ai.json_utils import parse_json_payload
from backend.services.ai.gateway import complete as chat_completion


async def analyze_api_failure(
    db: Session,
    *,
    project: Project,
    artifact: AiArtifact | None,
    execution_result: dict[str, Any],
    script_content: str = "",
) -> dict[str, Any]:
    artifact_meta = {
        "artifact_id": artifact.id if artifact else None,
        "case_id": artifact.case_id if artifact else None,
        "title": artifact.title if artifact else None,
    }
    user_prompt = f"""【任务】分析接口自动化 DSL 执行失败原因，并给出可操作的修复建议。

【产物信息】
{json.dumps(artifact_meta, ensure_ascii=False)}

【DSL 脚本摘要】
{(script_content or "")[:6000]}

【执行结果】
{json.dumps(execution_result, ensure_ascii=False)[:8000]}

请返回 JSON：
{{
  "root_cause": "根因简述",
  "failed_steps": [{{"index": 0, "name": "", "reason": ""}}],
  "fix_suggestions": ["建议1", "建议2"],
  "dsl_patch_hint": "可选的 DSL 修改提示"
}}
"""
    llm = await chat_completion(
        system_prompt="你是接口自动化测试专家，擅长 httpx DSL 断言失败定位。",
        user_prompt=user_prompt,
        profile="bulk_local",
        json_mode=True,
    )
    try:
        payload = parse_json_payload(llm.content)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "root_cause": "AI 解析失败",
            "failed_steps": [],
            "fix_suggestions": [str(exc)],
            "dsl_patch_hint": "",
        }
    return {
        "model": llm.model,
        "analysis": payload,
        "used_fallback": llm.used_fallback,
    }
