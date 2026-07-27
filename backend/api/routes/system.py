from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.db.session import get_db
from backend.schemas.dto import SystemOverviewOut
from backend.services.system_service import build_system_overview

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=dict)
def get_health() -> dict:
    return {"status": "ok"}


@router.get("/overview", response_model=SystemOverviewOut, dependencies=[Depends(require_permission("system.read"))])
def get_system_overview(db: Session = Depends(get_db)) -> SystemOverviewOut:
    return build_system_overview(db)
