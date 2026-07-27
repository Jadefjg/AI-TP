from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_project
from backend.core.config import get_settings
from backend.db.session import get_db
from backend.models.entities import CiWebhookDelivery, Project
from backend.schemas.dto import CiWebhookConfigOut, CiWebhookConfigUpdate
from backend.services.audit_service import log_action
from backend.services import ci_webhook_service

router = APIRouter(tags=["ci-integrations"])
mgmt_router = APIRouter(prefix="/projects", tags=["ci-integrations"])


@mgmt_router.get(
    "/{project_id}/integrations/ci",
    response_model=CiWebhookConfigOut,
    dependencies=[Depends(require_permission("integration.ci.read"))],
)
def get_ci_config(project: Project = Depends(get_tenant_project), db: Session = Depends(get_db)) -> dict:
    cfg = ci_webhook_service.get_or_create_config(db, project)
    base = (get_settings().ci_webhook_public_base_url or "http://127.0.0.1:8001").rstrip("/")
    secret = cfg.secret
    masked = f"{secret[:4]}…{secret[-4:]}" if len(secret) > 8 else "****"
    return {
        "project_id": project.id,
        "enabled": cfg.enabled,
        "provider": cfg.provider,
        "default_kinds": cfg.default_kinds or ["unit", "api"],
        "default_branch": cfg.default_branch,
        "pr_comment_enabled": cfg.pr_comment_enabled,
        "github_repo": cfg.github_repo,
        "webhook_url_hint": f"{base}/integrations/ci/{project.id}/webhook",
        "secret_masked": masked,
    }


@mgmt_router.put(
    "/{project_id}/integrations/ci",
    response_model=CiWebhookConfigOut,
    dependencies=[Depends(require_permission("integration.ci.manage"))],
)
def update_ci_config(
    body: CiWebhookConfigUpdate,
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
) -> dict:
    cfg = ci_webhook_service.get_or_create_config(db, project)
    data = body.model_dump(exclude_unset=True)
    if data.pop("rotate_secret", False):
        cfg.secret = ci_webhook_service.generate_secret()
    for key, value in data.items():
        if key == "github_token" and value is None:
            continue
        setattr(cfg, key, value)
    db.commit()
    db.refresh(cfg)
    log_action(
        db,
        module="integrations",
        action="ci.config_updated",
        message=f"CI webhook config project #{project.id}",
        organization_id=project.organization_id,
        project_id=project.id,
    )
    return get_ci_config(project=project, db=db)


@mgmt_router.get(
    "/{project_id}/integrations/ci/deliveries",
    dependencies=[Depends(require_permission("integration.ci.read"))],
)
def list_deliveries(
    project: Project = Depends(get_tenant_project),
    db: Session = Depends(get_db),
    limit: int = 20,
) -> list[dict]:
    rows = (
        db.query(CiWebhookDelivery)
        .filter(CiWebhookDelivery.project_id == project.id)
        .order_by(CiWebhookDelivery.id.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        {
            "id": r.id,
            "delivery_key": r.delivery_key,
            "run_id": r.run_id,
            "provider": r.provider,
            "ref": r.ref,
            "pr_number": r.pr_number,
            "pr_comment_posted": r.pr_comment_posted,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/integrations/ci/{project_id}/webhook")
async def ci_webhook(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    x_ci_token: str | None = Header(default=None, alias="X-CI-Token"),
) -> dict:
    project = db.query(Project).filter(Project.id == project_id).one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    cfg = ci_webhook_service.get_or_create_config(db, project)
    ci_webhook_service.verify_ci_token(cfg, x_ci_token)
    payload = await request.json()
    provider = request.headers.get("X-GitHub-Event") and "github" or cfg.provider
    result = ci_webhook_service.trigger_run_from_webhook(
        db,
        project=project,
        config=cfg,
        payload=payload if isinstance(payload, dict) else {},
        provider=provider,
    )
    log_action(
        db,
        module="integrations",
        action="ci.webhook_received",
        message=f"CI webhook project #{project_id}",
        organization_id=project.organization_id,
        project_id=project.id,
        detail={"result": result},
    )
    return result
