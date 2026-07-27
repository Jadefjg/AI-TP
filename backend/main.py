import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    ai,
    auth,
    cases,
    ci_integrations,
    test_organization,
    api_automation_routes,
    ui_automation_routes,
    workbench,
    perf_monitoring,
    dashboard,
    internal_worker,
    knowledge,
    logs,
    billing,
    organization_members,
    organizations,
    projects,
    rbac,
    reports,
    runs,
    settings as settings_routes,
    system,
    workers,
)
from backend.api.metrics_auth import verify_metrics_access
from backend.core.config import get_settings
from backend.core.version import APP_VERSION
from backend.db.bootstrap import bootstrap_schema
from backend.services.job_queue import recover_stale_execution_jobs, start_job_worker

logger = logging.getLogger(__name__)

app = FastAPI(title="AI 测试平台", version=APP_VERSION)
app_settings = get_settings()

if app_settings.metrics_enabled:
    from backend.core.tracing import PrometheusMiddleware, RequestTracingMiddleware

    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestTracingMiddleware)
else:
    from backend.core.tracing import RequestTracingMiddleware

    app.add_middleware(RequestTracingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(organizations.router)
app.include_router(organization_members.router)
app.include_router(billing.org_router)
app.include_router(billing.router)
app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(workbench.router)
app.include_router(ci_integrations.mgmt_router)
app.include_router(ci_integrations.router)
app.include_router(ui_automation_routes.router)
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(test_organization.router)
app.include_router(api_automation_routes.router)
app.include_router(perf_monitoring.router)
app.include_router(knowledge.router)
app.include_router(runs.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(rbac.router)
app.include_router(logs.router)
app.include_router(settings_routes.router)
app.include_router(system.router)
app.include_router(workers.router)
app.include_router(internal_worker.router)

_instrumentor_cls = None
try:
    from backend.core.tracing import setup_tracing

    _instrumentor_cls = setup_tracing()
except Exception:  # noqa: BLE001
    logger.debug("tracing setup skipped", exc_info=True)

if _instrumentor_cls is not None:
    _instrumentor_cls().instrument_app(app)


@app.on_event("startup")
def _startup() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
    bootstrap_schema()
    try:
        recovered = recover_stale_execution_jobs()
        if recovered:
            logger.warning("recovered %s stale execution job(s) on startup", recovered)
    except Exception:  # noqa: BLE001
        logger.exception("stale job recovery failed")
    backend = (app_settings.job_queue_backend or "db").strip().lower()
    if app_settings.job_worker_enabled and app_settings.job_worker_in_api:
        if backend in {"rq", "celery"}:
            logger.info(
                "embedded job worker disabled for JOB_QUEUE_BACKEND=%s; run dedicated worker process",
                backend,
            )
        else:
            start_job_worker()


@app.get("/")
def index() -> dict:
    return {
        "name": "AI 测试平台 API",
        "version": app.version,
        "docs": "/docs",
        "health": "ok",
        "ai_modules": "/ai/modules",
    }


@app.get("/metrics", dependencies=[Depends(verify_metrics_access)])
def prometheus_metrics() -> Response:
    from backend.core.metrics import metrics_payload

    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)
