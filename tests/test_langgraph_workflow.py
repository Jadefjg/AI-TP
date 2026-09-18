import asyncio
import pytest

from backend.services.agents.langgraph_workflow import (
    AGENT_KEYS,
    _after_handoff,
    _next_route,
    _retry_route,
    build_agent_graph,
    build_full_agent_graph,
    retry_agent_graph,
)


def test_langgraph_graphs_compile_with_checkpoint_support():
    assert build_agent_graph() is not None
    assert build_full_agent_graph() is not None


def test_routes_are_sequential_and_retry_current_agent():
    assert _next_route({"status": "completed", "current_index": 0}) == "handoff"
    assert _after_handoff({"current_index": 0}) == "functional_case"
    assert _retry_route({"current_index": 3}) == AGENT_KEYS[3]
    assert _next_route({"status": "pending_review", "current_index": 1}) == "end"


def test_retry_rejects_unknown_agent_without_touching_checkpoint():
    with pytest.raises(ValueError, match="unsupported retry agent"):
        asyncio.run(retry_agent_graph(thread_id="t", agent_key="unknown"))


def test_persistent_backend_fails_loudly_without_connection(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid-host/db")
    with pytest.raises(RuntimeError, match="checkpointer"):
        build_agent_graph()
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER", "memory")
