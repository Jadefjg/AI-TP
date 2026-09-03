"""Operations management APIs: overview, dictionaries, scheduled jobs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user, require_any_permission, require_permission
from backend.db.session import get_db
from backend.models.entities import User
from backend.schemas.dto import (
    DictionaryCreate,
    DictionaryItemCreate,
    DictionaryItemOut,
    DictionaryOut,
    ScheduledJobCreate,
    ScheduledJobOut,
    ScheduledJobRunOut,
)
from backend.services.audit_service import log_action
from backend.services.dictionary_service import (
    delete_dictionary,
    list_dictionaries,
    seed_builtin_dictionaries,
    upsert_dictionary,
    upsert_dictionary_item,
)
from backend.services.ops_overview_service import build_ops_overview
from backend.services.scheduled_job_service import (
    list_handler_catalog,
    list_job_runs,
    list_jobs,
    run_job,
    seed_default_scheduled_jobs,
    set_job_enabled,
    upsert_job,
)

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get(
    "/overview",
    dependencies=[Depends(require_any_permission("ops.read", "system.read", "settings.read"))],
)
def ops_overview(db: Session = Depends(get_db)) -> dict:
    return build_ops_overview(db)


@router.get("/dictionaries", response_model=list[DictionaryOut], dependencies=[Depends(require_permission("dict.read"))])
def dictionaries_list(active_only: bool = False, db: Session = Depends(get_db)) -> list:
    return list_dictionaries(db, active_only=active_only)


@router.post("/dictionaries", response_model=DictionaryOut, dependencies=[Depends(require_permission("dict.write"))])
def dictionaries_upsert(body: DictionaryCreate, db: Session = Depends(get_db)) -> object:
    row = upsert_dictionary(
        db,
        code=body.code.strip(),
        name=body.name.strip(),
        description=body.description,
        is_active=body.is_active,
    )
    log_action(db, module="ops", action="dict.upsert", message=f"dictionary {row.code} upserted")
    return row


@router.post("/dictionaries/seed", dependencies=[Depends(require_permission("dict.write"))])
def dictionaries_seed(db: Session = Depends(get_db)) -> dict:
    seed_builtin_dictionaries(db)
    return {"ok": True}


@router.post(
    "/dictionaries/{dictionary_id}/items",
    response_model=DictionaryItemOut,
    dependencies=[Depends(require_permission("dict.write"))],
)
def dictionaries_upsert_item(dictionary_id: int, body: DictionaryItemCreate, db: Session = Depends(get_db)) -> object:
    try:
        row = upsert_dictionary_item(
            db,
            dictionary_id=dictionary_id,
            item_key=body.item_key.strip(),
            item_label=body.item_label.strip(),
            item_value=body.item_value,
            sort_order=body.sort_order,
            is_active=body.is_active,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_action(
        db,
        module="ops",
        action="dict.item_upsert",
        message=f"dictionary item {body.item_key} upserted",
        detail={"dictionary_id": dictionary_id},
    )
    return row


@router.delete("/dictionaries/{dictionary_id}", dependencies=[Depends(require_permission("dict.write"))])
def dictionaries_delete(dictionary_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        delete_dictionary(db, dictionary_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_action(db, module="ops", action="dict.delete", message=f"dictionary #{dictionary_id} deleted")
    return {"ok": True}


@router.get("/schedule/handlers", dependencies=[Depends(require_permission("schedule.read"))])
def schedule_handlers() -> list[dict]:
    return list_handler_catalog()


@router.get("/schedule/jobs", response_model=list[ScheduledJobOut], dependencies=[Depends(require_permission("schedule.read"))])
def schedule_jobs(db: Session = Depends(get_db)) -> list:
    return list_jobs(db)


@router.post("/schedule/jobs", response_model=ScheduledJobOut, dependencies=[Depends(require_permission("schedule.write"))])
def schedule_jobs_upsert(body: ScheduledJobCreate, db: Session = Depends(get_db)) -> object:
    try:
        row = upsert_job(
            db,
            name=body.name.strip(),
            handler_key=body.handler_key.strip(),
            description=body.description,
            interval_seconds=body.interval_seconds,
            enabled=body.enabled,
            params=body.params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_action(db, module="ops", action="schedule.upsert", message=f"job {row.name} upserted")
    return row


@router.post(
    "/schedule/jobs/{job_id}/enable",
    response_model=ScheduledJobOut,
    dependencies=[Depends(require_permission("schedule.write"))],
)
def schedule_job_enable(job_id: int, enabled: bool = True, db: Session = Depends(get_db)) -> object:
    try:
        return set_job_enabled(db, job_id, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/schedule/jobs/{job_id}/run",
    response_model=ScheduledJobRunOut,
    dependencies=[Depends(require_permission("schedule.write"))],
)
def schedule_job_run(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> object:
    _ = user
    try:
        return run_job(db, job_id, trigger="manual")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/schedule/jobs/{job_id}/runs",
    response_model=list[ScheduledJobRunOut],
    dependencies=[Depends(require_permission("schedule.read"))],
)
def schedule_job_runs(job_id: int, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list:
    return list_job_runs(db, job_id, limit=limit)


@router.post("/schedule/seed", dependencies=[Depends(require_permission("schedule.write"))])
def schedule_seed(db: Session = Depends(get_db)) -> dict:
    seed_default_scheduled_jobs(db)
    return {"ok": True}
