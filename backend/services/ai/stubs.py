from __future__ import annotations

import json

from backend.services.ai.constants import (
    MODULE_API_AUTOMATION,
    MODULE_FUNCTIONAL_CASES,
    MODULE_OPENAPI_SPEC,
    MODULE_PERF_PLAN,
    MODULE_REQUIREMENT_REVIEW,
    MODULE_SECURITY_SCAN,
)


def _extract_requirement_text(user_prompt: str) -> str:
    marker = "【待评审需求内容】"
    if marker in user_prompt:
        return user_prompt.split(marker, 1)[1].strip()
    return user_prompt.strip()


def _api_automation_stub() -> dict:
    return {
        "script_content": (
            'version: "1"\n'
            "steps:\n"
            "  - name: health_check\n"
            "    request:\n"
            "      method: GET\n"
            "      url: {{base_url}}/system/health\n"
            "    assert:\n"
            "      status: 200\n"
            "  - name: api_root\n"
            "    request:\n"
            "      method: GET\n"
            "      url: {{base_url}}/\n"
            "    assert:\n"
            "      status: 200\n"
        ),
        "remark": "stub 接口 DSL：仅探测公开端点，填写 Base URL 后可直接执行",
    }


def _perf_plan_stub() -> dict:
    return {
        "press_mode": "step",
        "start_concurrency": 5,
        "max_concurrency": 30,
        "step": 5,
        "duration": 60,
        "warmup": 10,
        "api_weight": [{"api_path": "/system/health", "weight": 100}],
        "warning_rule": {"rt_limit": 500, "err_rate_limit": 1},
    }


def _security_scan_stub() -> list:
    return [
        {
            "vul_type": "SQL注入",
            "risk_level": "高",
            "test_payload": ["' OR '1'='1", "1;--", "1 UNION SELECT NULL--"],
            "scan_strategy": "对字符串入参逐字段替换并观察 5xx/SQL 错误特征（stub）",
        },
        {
            "vul_type": "XSS",
            "risk_level": "中",
            "test_payload": ["<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>"],
            "scan_strategy": "反射型参数回显检测（stub）",
        },
        {
            "vul_type": "路径穿越",
            "risk_level": "中",
            "test_payload": ["../../etc/passwd", "..%2F..%2Fetc%2Fpasswd"],
            "scan_strategy": "对文件路径类参数注入相对路径探测（stub）",
        },
    ]


def _extract_req_content(user_prompt: str) -> str:
    text = (user_prompt or "").strip()
    if not text:
        return ""
    for marker in ("需求：", "需求:", "【待评审需求正文】", "【待评审需求内容】"):
        if marker in text:
            tail = text.split(marker, 1)[1]
            for stop in ("接口文档：", "接口文档:", "【项目知识库参考"):
                if stop in tail:
                    tail = tail.split(stop, 1)[0]
            return tail.strip()
    return text[:500]


def _functional_cases_stub(user_prompt: str, *, requirement_text: str | None = None) -> list:
    req = (requirement_text or _extract_req_content(user_prompt)).replace("\n", " ").strip()
    summary = req[:80] if req else "需求场景"
    return [
        {
            "case_name": f"主流程可用性（stub） {summary}",
            "module": "核心流程",
            "precondition": "系统可访问，测试账号可用",
            "operate_step": "准备数据;执行主流程;校验结果",
            "expect_result": "主流程成功完成",
        },
        {
            "case_name": "异常输入校验（stub）",
            "module": "输入校验",
            "precondition": None,
            "operate_step": "输入非法参数;提交请求",
            "expect_result": "返回明确错误码与提示",
        },
        {
            "case_name": f"边界条件覆盖（stub） {summary[:40]}",
            "module": "边界场景",
            "precondition": "准备边界测试数据",
            "operate_step": "输入边界值;提交请求;观察系统行为",
            "expect_result": "边界值处理符合需求约定",
        },
    ]


def _openapi_stub(user_prompt: str) -> dict:
    title = "Project API"
    for line in user_prompt.splitlines():
        if line.strip().startswith("项目名称:"):
            title = f"{line.split(':', 1)[1].strip() or 'Project'} API"
            break
    methods_paths: list[tuple[str, str]] = []
    for line in user_prompt.splitlines():
        text = line.strip().lstrip("- ").strip()
        parts = text.split()
        if len(parts) >= 2 and parts[0].upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            methods_paths.append((parts[0].upper(), parts[1]))
    if not methods_paths:
        methods_paths = [("GET", "/system/health"), ("GET", "/")]
    paths: dict = {}
    for method, path in methods_paths[:40]:
        paths.setdefault(path, {})[method.lower()] = {
            "summary": f"{method} {path}",
            "operationId": f"{method.lower()}_{path.strip('/').replace('/', '_') or 'root'}",
            "responses": {"200": {"description": "Successful response"}},
        }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": "1.0.0",
            "description": "stub OpenAPI：模型不可用时基于项目/路由信号生成",
        },
        "paths": paths,
    }


def build_stub_payload(
    *,
    system_prompt: str,
    user_prompt: str,
    profile: str,
    module_type: str | None = None,
    requirement_text: str | None = None,
) -> str:
    if module_type == MODULE_REQUIREMENT_REVIEW:
        from backend.services.requirement_analyzer import analyze_requirement_heuristic

        text = requirement_text or _extract_requirement_text(user_prompt)
        return json.dumps(analyze_requirement_heuristic(text), ensure_ascii=False)

    if module_type == MODULE_OPENAPI_SPEC:
        return json.dumps(_openapi_stub(user_prompt), ensure_ascii=False)

    if module_type == MODULE_API_AUTOMATION:
        return json.dumps(_api_automation_stub(), ensure_ascii=False)

    if module_type == MODULE_PERF_PLAN:
        return json.dumps(_perf_plan_stub(), ensure_ascii=False)

    if module_type == MODULE_SECURITY_SCAN:
        return json.dumps(_security_scan_stub(), ensure_ascii=False)

    if module_type == MODULE_FUNCTIONAL_CASES:
        return json.dumps(_functional_cases_stub(user_prompt, requirement_text=requirement_text), ensure_ascii=False)

    # Legacy keyword fallback for custom / unknown prompts
    text = f"{system_prompt}\n{user_prompt}"
    if "需求预评审" in text or "ambiguity_list" in text:
        payload = {
            "ambiguity_list": [
                {
                    "pos": "需求概述",
                    "level": "中",
                    "desc": "部分业务规则描述不够量化（stub）",
                    "suggest": "补充输入边界、状态机与异常分支",
                }
            ],
            "miss_logic_list": [],
            "untestable_list": [],
            "biz_risk_list": [
                {
                    "pos": "资金/权限相关流程",
                    "level": "高",
                    "desc": "未明确失败补偿与幂等策略（stub）",
                    "suggest": "补充回滚、重试与审计要求",
                }
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    if "功能测试用例" in text or "case_name" in text:
        return json.dumps(_functional_cases_stub(user_prompt, requirement_text=requirement_text), ensure_ascii=False)

    if "DSL" in text or "script_content" in text:
        return json.dumps(_api_automation_stub(), ensure_ascii=False)

    if "openapi" in text.lower() or "swagger" in text.lower() or '"paths"' in text:
        return json.dumps(_openapi_stub(user_prompt), ensure_ascii=False)

    if "压测" in text or "press_mode" in text:
        return json.dumps(_perf_plan_stub(), ensure_ascii=False)

    if "OWASP" in text or "vul_type" in text:
        return json.dumps(_security_scan_stub(), ensure_ascii=False)

    _ = profile
    return json.dumps({"message": "stub response"}, ensure_ascii=False)
