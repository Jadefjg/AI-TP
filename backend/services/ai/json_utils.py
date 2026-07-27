from __future__ import annotations

import json
import re
from typing import Any

from backend.services.requirement_analyzer import REVIEW_LIST_KEYS


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _repair_json_text(text: str) -> str:
    value = (text or "").strip()
    value = value.replace("\ufeff", "")
    value = value.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    value = re.sub(r",\s*}", "}", value)
    value = re.sub(r",\s*]", "]", value)
    return value


def _try_load_json(text: str) -> Any | None:
    try:
        return json.loads(_repair_json_text(text))
    except json.JSONDecodeError:
        return None


def parse_json_payload(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        raise ValueError("模型返回为空")

    direct = _try_load_json(text)
    if direct is not None:
        return direct

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        parsed = _try_load_json(fenced.group(1).strip())
        if parsed is not None:
            return parsed

    for pattern in (
        r"\{[\s\S]*\"ambiguity_list\"[\s\S]*\}",
        r"\{[\s\S]*\"miss_logic_list\"[\s\S]*\}",
        r"\[[\s\S]*\]",
        r"\{[\s\S]*\}",
    ):
        for match in re.finditer(pattern, text):
            snippet = match.group(0)
            for end in range(len(snippet), 0, -1):
                parsed = _try_load_json(snippet[:end])
                if parsed is not None:
                    return parsed

    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start >= 0:
        snippet = text[start:]
        for end in range(len(snippet), 0, -1):
            parsed = _try_load_json(snippet[:end])
            if parsed is not None:
                return parsed

    raise ValueError("模型返回不是有效 JSON")


def parse_requirement_review_response(content: str) -> dict[str, Any]:
    payload = parse_json_payload(content)
    if not isinstance(payload, dict):
        raise ValueError("模型返回不是有效 JSON 对象")
    if any(isinstance(payload.get(key), list) for key in REVIEW_LIST_KEYS):
        return payload
    if payload.get("error") or payload.get("message"):
        raise ValueError(str(payload.get("error") or payload.get("message") or "模型未返回评审结果"))
    raise ValueError("模型返回缺少评审字段")
