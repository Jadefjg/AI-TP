from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentManifest:
    key: str
    label: str
    module_type: str
    engine: str
    generate: str
    execute: str
    layer: str = "business+execution"


@dataclass
class AgentExecuteResult:
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
