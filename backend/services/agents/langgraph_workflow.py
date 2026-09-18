"""LangGraph orchestration for the six business Agents.

The adapter keeps the platform runnable when LangGraph is not installed (for
minimal API deployments), while using StateGraph when the optional dependency
is present.  Existing Agent implementations remain the source of truth.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, TypedDict

from backend.services.agents.protocol import normalize_result


class AgentGraphState(TypedDict, total=False):
    agent_key: str
    input: dict[str, Any]
    result: dict[str, Any]
    trace: list[dict[str, Any]]
    db: Any
    project: Any
    review_required: bool
    review_approved: bool
    retry_count: int
    next_agent: str
    error: str
    current_index: int
    status: str


AGENT_KEYS = ("requirement", "functional_case", "ui", "interface", "perf", "security")
_CHECKPOINTER = None


def _compile(graph):
    """Compile with an in-process checkpointer when available.

    ``thread_id`` supplied by callers makes review resumes and duplicate
    requests address the same graph state. Deployments can replace this with a
    durable saver without changing the graph API.
    """
    global _CHECKPOINTER
    backend = os.getenv("LANGGRAPH_CHECKPOINTER", "memory").lower()
    if backend in {"redis", "postgres", "postgresql"}:
        try:
            if backend == "redis":
                from langgraph.checkpoint.redis import RedisSaver
                saver = RedisSaver.from_conn_string(os.environ["REDIS_URL"])
            else:
                from langgraph.checkpoint.postgres import PostgresSaver
                saver = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])
            saver.setup()
            return graph.compile(checkpointer=saver)
        except (ImportError, KeyError, TypeError, ValueError):
            # Keep local/test deployments bootable when the optional backend
            # package or service is absent; production should monitor this.
            pass
    try:
        from langgraph.checkpoint.memory import MemorySaver
        if _CHECKPOINTER is None:
            _CHECKPOINTER = MemorySaver()
        return graph.compile(checkpointer=_CHECKPOINTER)
    except (ImportError, TypeError):
        return graph.compile()


def validate_handoff_node(state: AgentGraphState) -> AgentGraphState:
    """Validate the typed handoff before allowing the next node to run."""
    from backend.services.agents.artifact_adapters import build_validated_handoff
    target = state.get("next_agent")
    if not target or not state.get("result"):
        return state
    module = {"functional_case": "functional_cases", "ui": "ui_automation", "interface": "api_automation", "perf": "perf_plan", "security": "security_scan"}.get(target, target)
    handoff = build_validated_handoff(module, run_input=state.get("input", {}), result=state["result"])
    return {**state, "input": handoff["input"], "handoff": handoff,
            "current_index": int(state.get("current_index", 0)) + 1,
            "retry_count": 0}


def review_gate_node(state: AgentGraphState) -> AgentGraphState:
    """Pause marker for human review; the API/DB supplies approval later."""
    if state.get("review_required") and not state.get("review_approved"):
        return {**state, "status": "pending_review"}
    return {**state, "status": "approved" if state.get("review_required") else "completed"}


def retry_node(state: AgentGraphState) -> AgentGraphState:
    attempts = int(state.get("retry_count", 0)) + 1
    if attempts > 2:
        return {**state, "status": "failed", "error": state.get("error", "agent execution failed")}
    return {**state, "retry_count": attempts, "status": "retrying"}


def _next_route(state: AgentGraphState) -> str:
    """Route without fan-out; this is deliberately a pure function for replay."""
    if state.get("status") == "pending_review":
        return "end"
    if state.get("status") == "failed":
        return "retry" if int(state.get("retry_count", 0)) < 3 else "end"
    if state.get("current_index", 0) + 1 >= len(AGENT_KEYS):
        return "end"
    return "handoff"


def _after_handoff(state: AgentGraphState) -> str:
    index = int(state.get("current_index", 0)) + 1
    return AGENT_KEYS[index] if index < len(AGENT_KEYS) else "end"


def _retry_route(state: AgentGraphState) -> str:
    index = min(int(state.get("current_index", 0)), len(AGENT_KEYS) - 1)
    return AGENT_KEYS[index]


async def execute_agent_node(state: AgentGraphState) -> AgentGraphState:
    """Execute one Agent and normalize its output to AgentResult."""
    from backend.services.agents import interface_agent, perf_agent, requirement_agent, security_agent
    key = state["agent_key"]
    payload = state.get("input", {})
    try:
        if key == "requirement":
            call = requirement_agent.review(state["db"], state["project"], requirement_text=payload.get("requirement_text", ""))
        elif key == "functional_case":
            call = requirement_agent.generate_case_artifact(state["db"], state["project"], requirement_text=payload.get("requirement_text", ""))
        elif key == "interface":
            call = interface_agent.generate(state["db"], state["project"], case_info=str(payload.get("case_info", "")), api_info=str(payload.get("api_info", "")))
        elif key == "perf":
            call = perf_agent.generate(state["db"], state["project"], biz_desc=str(payload.get("biz_desc", "")), api_doc=str(payload.get("api_doc", "")))
        elif key == "security":
            call = security_agent.generate(state["db"], state["project"], api_params=str(payload.get("api_params", "")))
        elif key == "ui":
            call = None
        else:
            raise ValueError(f"unsupported agent key: {key}")
        value = {"status": "completed", "payload": payload, "output_type": "ui_automation"} if key == "ui" else await asyncio.wait_for(call, timeout=float(os.getenv("AGENT_TIMEOUT_SECONDS", "120")))
    except Exception as exc:
        return {**state, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "agent_key": key}
    result = normalize_result(key, value).model_dump(mode="json")
    next_index = AGENT_KEYS.index(key) + 1 if key in AGENT_KEYS else len(AGENT_KEYS)
    next_agent = AGENT_KEYS[next_index] if next_index < len(AGENT_KEYS) else None
    return {**state, "result": result,
            "trace": [*(state.get("trace") or []), result.get("trace", {})],
            "next_agent": next_agent,
            "status": result.get("status", "completed")}


def build_agent_graph():
    """Build a single-node LangGraph for worker execution.

    A single node is intentional: Workflow DB rows provide the durable edges
    and approval gates. LangGraph handles execution/state normalization per step.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None
    graph = StateGraph(AgentGraphState)
    graph.add_node("agent", execute_agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return _compile(graph)


def build_full_agent_graph():
    """Build a deterministic sequential graph with review and retry gates.

    A single router is used after each step.  Defining static edges from a
    shared handoff node to every Agent causes LangGraph to fan out; tracking the
    current index keeps execution strictly ordered and makes replay idempotent.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None
    graph = StateGraph(AgentGraphState)
    async def run_step(state: AgentGraphState, key: str) -> AgentGraphState:
        return await execute_agent_node({**state, "agent_key": key})

    for key in AGENT_KEYS:
        graph.add_node(key, lambda state, _key=key: run_step(state, _key))
    graph.add_node("handoff", validate_handoff_node)
    graph.add_node("review", review_gate_node)
    graph.add_node("retry", retry_node)
    graph.set_entry_point("requirement")
    for index, key in enumerate(AGENT_KEYS):
        graph.add_edge(key, "review")
    graph.add_conditional_edges("review", _next_route, {"handoff": "handoff", "retry": "retry", "end": END})
    graph.add_conditional_edges("handoff", _after_handoff, {**{k: k for k in AGENT_KEYS}, "end": END})
    graph.add_conditional_edges("retry", _retry_route, {k: k for k in AGENT_KEYS})
    return _compile(graph)


async def invoke_full_agent_graph(*, payload: dict[str, Any], db: Any, project: Any, review_approved: bool = False, thread_id: str | None = None, workflow_id: int | None = None) -> dict[str, Any]:
    if not thread_id and workflow_id and db is not None:
        try:
            from backend.models.entities import AgentWorkflowRun
            run = db.query(AgentWorkflowRun).filter_by(id=workflow_id, project_id=project.id).one_or_none()
            thread_id = run.thread_id if run else None
        except Exception:
            thread_id = None
    state: AgentGraphState = {"input": payload, "trace": [], "db": db, "project": project, "review_approved": review_approved, "retry_count": 0, "current_index": 0}
    graph = build_full_agent_graph()
    if graph is not None:
        config = {"configurable": {"thread_id": thread_id or f"project:{getattr(project, 'id', 'unknown')}"}}
        return await graph.ainvoke(state, config=config)
    # Minimal deployments execute the first node and return a resumable state;
    # DB Workflow progression invokes subsequent nodes after approval.
    state["agent_key"] = "requirement"
    return await execute_agent_node(state)


async def invoke_agent_graph(*, agent_key: str, payload: dict[str, Any], db: Any, project: Any) -> dict[str, Any]:
    state: AgentGraphState = {"agent_key": agent_key, "input": payload, "trace": [], "db": db, "project": project}
    graph = build_agent_graph()
    if graph is not None:
        return await graph.ainvoke(state)
    return await execute_agent_node(state)
