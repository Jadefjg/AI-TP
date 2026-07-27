from __future__ import annotations

import re
from typing import Any

import yaml

_VAR_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")


def substitute_vars(text: str, variables: dict[str, str]) -> str:
    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return _VAR_PATTERN.sub(_repl, text or "")


def parse_dsl(script_content: str, variables: dict[str, str] | None = None) -> dict[str, Any]:
    vars_map = variables or {}
    rendered = substitute_vars(script_content, vars_map)
    data = yaml.safe_load(rendered)
    if not isinstance(data, dict):
        raise ValueError("DSL 根节点必须是对象")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("DSL 缺少 steps 数组")
    return data
