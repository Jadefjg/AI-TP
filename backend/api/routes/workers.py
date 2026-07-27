from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.db.session import get_db
from backend.models.entities import K6DispatchJob, K6WorkerNode
from backend.schemas.dto import K6DispatchJobOut, K6WorkerCreate, K6WorkerOut, K6WorkerUpdate
from backend.services.audit_service import log_action
from backend.services.engines.k6_scheduler import seed_default_worker

router = APIRouter(prefix="/admin/k6-workers", tags=["k6-workers"])


@router.get("", response_model=list[K6WorkerOut], dependencies=[Depends(require_permission("worker.read"))])
def list_workers(db: Session = Depends(get_db)) -> list[K6WorkerNode]:
    return db.query(K6WorkerNode).order_by(K6WorkerNode.id.asc()).all()


@router.post("", response_model=K6WorkerOut, dependencies=[Depends(require_permission("worker.manage"))])
def create_worker(body: K6WorkerCreate, db: Session = Depends(get_db)) -> K6WorkerNode:
    exists = db.query(K6WorkerNode).filter(K6WorkerNode.name == body.name).one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="worker name already exists")
    row = K6WorkerNode(
        name=body.name,
        endpoint=body.endpoint,
        mode=body.mode,
        weight=body.weight,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, module="workers", action="k6_worker.created", message=f"worker {row.name}")
    return row


@router.patch(
    "/{worker_id}",
    response_model=K6WorkerOut,
    dependencies=[Depends(require_permission("worker.manage"))],
)
def update_worker(worker_id: int, body: K6WorkerUpdate, db: Session = Depends(get_db)) -> K6WorkerNode:
    row = db.query(K6WorkerNode).filter(K6WorkerNode.id == worker_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="worker not found")
    if body.endpoint is not None:
        row.endpoint = body.endpoint
    if body.mode is not None:
        row.mode = body.mode
    if body.weight is not None:
        row.weight = body.weight
    if body.enabled is not None:
        row.enabled = body.enabled
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/{worker_id}/health-check",
    response_model=dict,
    dependencies=[Depends(require_permission("worker.read"))],
)
def health_check_worker(worker_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.query(K6WorkerNode).filter(K6WorkerNode.id == worker_id).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="worker not found")
    if row.mode == "local":
        row.last_health = "ok"
        db.commit()
        return {"worker": row.name, "status": "ok", "mode": "local"}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{row.endpoint.rstrip('/')}/system/health")
        row.last_health = "ok" if resp.status_code == 200 else "degraded"
        db.commit()
        return {"worker": row.name, "status": row.last_health, "http_status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        row.last_health = "down"
        db.commit()
        return {"worker": row.name, "status": "down", "reason": str(exc)}


@router.post("/seed-default", response_model=dict, dependencies=[Depends(require_permission("worker.manage"))])
def seed_workers(db: Session = Depends(get_db)) -> dict:
    seed_default_worker(db)
    return {"ok": True}


@router.get(
    "/dispatch-jobs",
    response_model=list[K6DispatchJobOut],
    dependencies=[Depends(require_permission("worker.read"))],
)
def list_dispatch_jobs(db: Session = Depends(get_db), limit: int = 50) -> list[K6DispatchJob]:
    return db.query(K6DispatchJob).order_by(K6DispatchJob.id.desc()).limit(limit).all()
