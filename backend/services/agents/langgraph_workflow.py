"""LangGraph orchestration for the six business Agents.

The adapter keeps the platform runnable when LangGraph is not installed (for
minimal API deployments), while using StateGraph when the optional dependency
is present.  Existing Agent implementations remain the source of truth.
"""
from __future__ import annotations

import asyncio
import atexit
import os
from uuid import uuid4
from typing import Any, TypedDict

from backend.services.agents.protocol import normalize_result


class AgentGraphState(TypedDict, total=False):
    agent_key: str
    input: dict[str, Any]
    result: dict[str, Any]
    results: dict[str, dict[str, Any]]
    trace: list[dict[str, Any]]
    project_id: int
    workflow_id: int
    review_required: bool
    review_approved: bool
    retry_count: int
    next_agent: str
    error: str
    current_index: int
    status: str


AGENT_KEYS = ("requirement", "functional_case", "ui", "interface", "perf", "security")
_CHECKPOINTER = None
_CHECKPOINTER_CONTEXT = None
_CHECKPOINTER_BACKEND = None


def _close_checkpointer() -> None:
    global _CHECKPOINTER_CONTEXT
    if _CHECKPOINTER_CONTEXT is not None:
        _CHECKPOINTER_CONTEXT.__exit__(None, None, None)
        _CHECKPOINTER_CONTEXT = None


atexit.register(_close_checkpointer)


def get_checkpointer():
    """Return one process-wide saver and keep context-managed connections alive."""
    global _CHECKPOINTER, _CHECKPOINTER_CONTEXT, _CHECKPOINTER_BACKEND
    backend = os.getenv("LANGGRAPH_CHECKPOINTER", "memory").lower()
    if _CHECKPOINTER is not None and _CHECKPOINTER_BACKEND == backend:
        return _CHECKPOINTER
    if _CHECKPOINTER is not None:
        _close_checkpointer()
        _CHECKPOINTER = None
    try:
        if backend == "redis":
            from langgraph.checkpoint.redis import RedisSaver
            candidate = RedisSaver.from_conn_string(os.environ["REDIS_URL"])
        elif backend in {"postgres", "postgresql"}:
            from langgraph.checkpoint.postgres import PostgresSaver
            candidate = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])
        else:
            from langgraph.checkpoint.memory import MemorySaver
            candidate = MemorySaver()
        if hasattr(candidate, "__enter__"):
            _CHECKPOINTER_CONTEXT = candidate
            candidate = candidate.__enter__()
        if hasattr(candidate, "setup"):
            candidate.setup()
        _CHECKPOINTER = candidate
        _CHECKPOINTER_BACKEND = backend
        return candidate
    except Exception as exc:
        if backend != "memory":
            raise RuntimeError(f"cannot initialize {backend} LangGraph checkpointer") from exc
        raise


def _compile(graph):
    """Compile with an in-process checkpointer when available.

    ``thread_id`` supplied by callers makes review resumes and duplicate
    requests address the same graph state. Deployments can replace this with a
    durable saver without changing the graph API.
    """
    try:
        return graph.compile(checkpointer=get_checkpointer())
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
    """Suspend the graph durably until an approval command is supplied."""
    if state.get("review_required") and not state.get("review_approved"):
        try:
            from langgraph.types import interrupt
            decision = interrupt({"workflow_id": state.get("workflow_id"),
                                  "agent_key": state.get("agent_key"),
                                  "result": state.get("result")})
            approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
            return {**state, "review_approved": approved,
                    "status": "approved" if approved else "failed",
                    "error": None if approved else "review rejected"}
        except ImportError:
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
    from backend.db.session import SessionLocal
    from backend.models.entities import Project
    from backend.services.agents import interface_agent, perf_agent, requirement_agent, security_agent, ui_agent
    key = state["agent_key"]
    payload = state.get("input", {})
    db = SessionLocal()
    try:
        project = db.query(Project).filter_by(id=state["project_id"]).one()
        if key == "requirement":
            call = requirement_agent.review(db, project, requirement_text=payload.get("requirement_text", ""))
        elif key == "functional_case":
            call = requirement_agent.generate_case_artifact(db, project, requirement_text=payload.get("requirement_text", ""))
        elif key == "interface":
            call = interface_agent.generate(db, project, case_info=str(payload.get("case_info", "")), api_info=str(payload.get("api_info", "")))
        elif key == "perf":
            call = perf_agent.generate(db, project, biz_desc=str(payload.get("biz_desc", "")), api_doc=str(payload.get("api_doc", "")))
        elif key == "security":
            call = security_agent.generate(db, project, api_params=str(payload.get("api_params", "")))
        elif key == "ui":
            case_id = payload.get("case_id")
            if not case_id:
                raise ValueError("case_id is required for UI Agent")
            value = ui_agent.generate(db, project, case_id=int(case_id))
        else:
            raise ValueError(f"unsupported agent key: {key}")
        if key != "ui":
            value = await asyncio.wait_for(call, timeout=float(os.getenv("AGENT_TIMEOUT_SECONDS", "120")))
    except Exception as exc:
        db.rollback()
        return {**state, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "agent_key": key}
    finally:
        db.close()
    result = normalize_result(key, value).model_dump(mode="json")
    result["module_type"] = {"requirement": "requirement_review", "functional_case": "functional_cases", "ui": "ui_automation", "interface": "api_automation", "perf": "perf_plan", "security": "security_scan"}[key]
    result["persisted_ids"] = [result["artifact_id"]] if result.get("artifact_id") else []
    next_index = AGENT_KEYS.index(key) + 1 if key in AGENT_KEYS else len(AGENT_KEYS)
    next_agent = AGENT_KEYS[next_index] if next_index < len(AGENT_KEYS) else None
    return {**state, "result": result,
            "results": {**(state.get("results") or {}), key: result},
            "trace": [*(state.get("trace") or []), *(result.get("trace") or [])],
            "next_agent": next_agent,
            "review_required": key in {"requirement", "perf", "security"},
            "review_approved": False,
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
    state: AgentGraphState = {"input": payload, "trace": [], "results": {}, "project_id": project.id,
                              "workflow_id": workflow_id or 0, "review_approved": review_approved,
                              "retry_count": 0, "current_index": 0}
    graph = build_full_agent_graph()
    if graph is not None:
        config = {"configurable": {"thread_id": thread_id or f"project:{getattr(project, 'id', 'unknown')}"}}
        return await graph.ainvoke(state, config=config)
    # Minimal deployments execute the first node and return a resumable state;
    # DB Workflow progression invokes subsequent nodes after approval.
    state["agent_key"] = "requirement"
    return await execute_agent_node(state)


async def resume_agent_graph(*, thread_id: str, approved: bool, note: str = "") -> dict[str, Any]:
    """Resume exactly the checkpoint suspended by a human-review interrupt."""
    from langgraph.types import Command
    graph = build_full_agent_graph()
    if graph is None:
        raise RuntimeError("LangGraph is required to resume a workflow")
    config = {"configurable": {"thread_id": thread_id}}
    return await graph.ainvoke(Command(resume={"approved": approved, "note": note}), config=config)


async def retry_agent_graph(*, thread_id: str, agent_key: str) -> dict[str, Any]:
    """Resume a failed checkpoint at the failed Agent, never from graph entry."""
    if agent_key not in AGENT_KEYS:
        raise ValueError(f"unsupported retry agent: {agent_key}")
    graph = build_full_agent_graph()
    if graph is None:
        raise RuntimeError("LangGraph is required to retry a workflow")
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise RuntimeError("workflow checkpoint not found")
    values = dict(snapshot.values)
    values.update({"agent_key": agent_key, "status": "retrying", "error": None,
                   "review_approved": False})
    # Updating as the failed node makes LangGraph continue along that node's
    # outgoing edge (review), preserving all previous results and handoffs.
    graph.update_state(config, values, as_node=agent_key)
    return await graph.ainvoke(None, config=config)


def project_graph_state(db: Any, *, workflow_id: int, state: dict[str, Any]) -> Any:
    """Project LangGraph's authoritative state onto query-only workflow rows."""
    from backend.models.entities import AgentWorkflowRun
    run = db.query(AgentWorkflowRun).filter_by(id=workflow_id).with_for_update().one()
    results = state.get("results") or {}
    for step in run.steps:
        result = results.get(step.agent_key)
        if not result:
            continue
        step.status = "failed" if result.get("status") == "failed" else "completed"
        step.detail = {**(step.detail or {}), "result": result}
        step.artifact_id = result.get("artifact_id")
        if step.agent_key in {"requirement", "perf", "security"} and step.agent_key == state.get("agent_key"):
            step.review_status = "pending_review" if state.get("__interrupt__") else step.review_status
    current = state.get("agent_key")
    if current in AGENT_KEYS:
        run.current_step = AGENT_KEYS.index(current)
    if state.get("status") == "failed":
        run.status = "failed"
    elif state.get("__interrupt__"):
        run.status = "pending_review"
    elif len(results) == len(AGENT_KEYS):
        run.status = "completed"
    else:
        run.status = "running"
    run.detail = {**(run.detail or {}), "langgraph": {"status": state.get("status"), "agent_key": current}}
    return run


async def invoke_agent_graph(*, agent_key: str, payload: dict[str, Any], db: Any, project: Any) -> dict[str, Any]:
    state: AgentGraphState = {"agent_key": agent_key, "input": payload, "trace": [],
                              "project_id": project.id}
    graph = build_agent_graph()
    if graph is not None:
        return await graph.ainvoke(state, config={"configurable": {"thread_id": f"single:{uuid4().hex}"}})
    return await execute_agent_node(state)
