"""Business-layer Agents: generate (AI Gateway) + execute (engines)."""
from __future__ import annotations

from backend.services.agents.base import AgentManifest
from backend.services.agents.interface_agent import InterfaceAgent
from backend.services.agents.perf_agent import PerfAgent
from backend.services.agents.requirement_agent import RequirementAgent
from backend.services.agents.security_agent import SecurityAgent
from backend.services.agents.ui_agent import UiAgent

requirement_agent = RequirementAgent()
ui_agent = UiAgent()
interface_agent = InterfaceAgent()
perf_agent = PerfAgent()
security_agent = SecurityAgent()

_AGENTS = {
    requirement_agent.manifest.key: requirement_agent,
    ui_agent.manifest.key: ui_agent,
    interface_agent.manifest.key: interface_agent,
    perf_agent.manifest.key: perf_agent,
    security_agent.manifest.key: security_agent,
}


def get_agent(key: str):
    agent = _AGENTS.get(key)
    if agent is None:
        raise ValueError(f"unknown agent: {key}")
    return agent


def list_agent_manifests() -> list[AgentManifest]:
    return [agent.manifest for agent in _AGENTS.values()]


__all__ = [
    "get_agent",
    "interface_agent",
    "list_agent_manifests",
    "perf_agent",
    "requirement_agent",
    "security_agent",
    "ui_agent",
]
