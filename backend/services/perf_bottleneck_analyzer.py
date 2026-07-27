from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.models.entities import K6DispatchJob, Project
from backend.services.ai.json_utils import parse_json_payload
from backend.services.ai.llm_client import chat_completion


async def analyze_perf_bottleneck(
    db: Session,
    *,
    project: Project,
    job: K6DispatchJob,
) -> dict[str, Any]:
    plan = job.plan_snapshot if isinstance(job.plan_snapshot, dict) else {}
    metrics = job.summary_metrics if isinstance(job.summary_metrics, dict) else {}
    nodes = job.node_results if isinstance(job.node_results, list) else []

    user_prompt = f"""【任务】根据 k6 压测结构化指标与执行分片结果，给出性能瓶颈分析与优化建议。

【压测方案】
{json.dumps(plan, ensure_ascii=False)[:4000]}

【汇总指标】
{json.dumps(metrics, ensure_ascii=False)}

【分片/节点结果摘要】
{json.dumps(nodes, ensure_ascii=False)[:6000]}

返回 JSON：
{{
  "bottlenecks": [{{"area": "", "severity": "高/中/低", "evidence": "", "suggestion": ""}}],
  "capacity_estimate": "容量评估简述",
  "tuning_actions": ["行动项1", "行动项2"]
}}
"""
    llm = await chat_completion(
        system_prompt="你是性能测试专家，熟悉 k6、RT/TPS/错误率分析与容量规划。",
        user_prompt=user_prompt,
        profile="high_precision",
        json_mode=True,
    )
    try:
        payload = parse_json_payload(llm.content)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "bottlenecks": [],
            "capacity_estimate": "",
            "tuning_actions": [f"AI 解析失败: {exc}"],
        }
    return {"model": llm.model, "analysis": payload, "job_id": job.id}
