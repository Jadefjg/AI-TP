from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import get_settings
from backend.services.engines.k6_scheduler import run_internal_k6_script

router = APIRouter(prefix="/internal", tags=["internal-worker"])


class K6RunIn(BaseModel):
    script: str = Field(min_length=1)
    timeout_sec: int = Field(default=600, ge=30, le=3600)


@router.post("/k6/run")
def internal_k6_run(
    body: K6RunIn,
    x_worker_token: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    expected = (settings.k6_worker_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="K6_WORKER_TOKEN is not configured; refusing unauthenticated internal k6 runs",
        )
    if x_worker_token != expected:
        raise HTTPException(status_code=403, detail="invalid worker token")
    return run_internal_k6_script(body.script, timeout_sec=body.timeout_sec)
