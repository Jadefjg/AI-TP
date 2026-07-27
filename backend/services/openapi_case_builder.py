from __future__ import annotations

import json
from typing import Any

import yaml


def parse_openapi_content(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("OpenAPI 内容为空，请粘贴 JSON 或 YAML")
    if len(text) < 10:
        raise ValueError("OpenAPI 内容过短，请粘贴完整的 OpenAPI/Swagger 文档（需包含 paths）")
    try:
        if text.startswith("{"):
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"OpenAPI 文档解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("OpenAPI 根节点必须是对象（JSON object / YAML mapping）")
    if "paths" not in data:
        raise ValueError("缺少 paths 字段：请确认粘贴的是 OpenAPI/Swagger 文档")
    return data


def _response_summary(responses: dict[str, Any] | None) -> str:
    if not responses:
        return "接口返回符合约定"
    parts: list[str] = []
    for code, meta in responses.items():
        if not isinstance(meta, dict):
            continue
        desc = meta.get("description") or ""
        parts.append(f"HTTP {code}: {desc}".strip())
    return "; ".join(parts) if parts else "接口返回符合约定"


def _build_steps(
    method: str,
    path: str,
    operation: dict[str, Any],
) -> list[str]:
    steps = [f"调用 {method.upper()} {path}"]
    params = operation.get("parameters") or []
    for param in params:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        location = param.get("in")
        required = param.get("required", False)
        if name and location:
            flag = "必填" if required else "可选"
            steps.append(f"准备 {location} 参数 {name}（{flag}）")
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        steps.append("构造并发送请求体")
    return steps


def build_case_skeletons(spec: dict[str, Any]) -> list[dict[str, Any]]:
    paths = spec.get("paths") or {}
    cases: list[dict[str, Any]] = []
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in http_methods or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId") or f"{method.lower()}_{path.strip('/').replace('/', '_')}"
            summary = operation.get("summary") or operation.get("description") or f"{method.upper()} {path}"
            tags = operation.get("tags") or []
            module = tags[0] if tags else path
            cases.append(
                {
                    "title": summary,
                    "module": module,
                    "preconditions": "服务可访问，测试环境已就绪",
                    "steps": _build_steps(method, path, operation),
                    "expected": _response_summary(operation.get("responses")),
                    "priority": "medium",
                    "source_requirement": "openapi",
                    "openapi_operation_id": operation_id,
                }
            )
    if not cases:
        raise ValueError("paths 中未找到可导入的 HTTP 接口（get/post/put/patch/delete 等）")
    return cases
