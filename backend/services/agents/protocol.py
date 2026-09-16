"""Runtime-neutral protocol shared by all specialized Agents."""
from __future__ import annotations

from typing import Any, Protocol
from sqlalchemy.orm import Session
from backend.models.entities import Project
from backend.schemas.agent import AgentResult


class BusinessAgent(Protocol):
    manifest: Any

    async def generate(self, db: Session, project: Project, **kwargs: Any) -> Any: ...

    def execute(self, *args: Any, **kwargs: Any) -> Any: ...


def normalize_result(agent_key: str, value: Any, *, trace=None, attempt: int = 1,
                     review_status: str = "not_required") -> AgentResult:
    """Convert legacy dict/AiTaskResult outputs to the common contract."""
    payload = getattr(value, "payload", value)
    ids = getattr(value, "persisted_ids", []) or []
    if isinstance(value, dict):
        status = str(value.get("status") or "completed")
        artifact_id = value.get("artifact_id") or value.get("job_id")
    else:
        status, artifact_id = "completed", (ids[0] if ids else None)
    status = {"passed": "completed", "success": "completed"}.get(status, status)
    return AgentResult(agent_key=agent_key, status=status, payload=payload,
                       artifact_id=artifact_id, attempt=attempt,
                       review_status=review_status, trace=trace or [])
