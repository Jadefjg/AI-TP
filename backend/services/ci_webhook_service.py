from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.entities import CiWebhookConfig, CiWebhookDelivery, Project, TestRun
from backend.services.job_queue import enqueue_test_run_job
from backend.services.orchestrator import create_run_with_items
from backend.services.plan_run_service import list_project_functional_case_ids


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def get_or_create_config(db: Session, project: Project) -> CiWebhookConfig:
    row = db.query(CiWebhookConfig).filter(CiWebhookConfig.project_id == project.id).one_or_none()
    if row:
        return row
    row = CiWebhookConfig(
        project_id=project.id,
        secret=generate_secret(),
        default_kinds=["unit", "api"],
        default_branch="main",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def verify_ci_token(config: CiWebhookConfig, token: str | None) -> None:
    if not config.enabled:
        raise HTTPException(status_code=403, detail="CI webhook disabled")
    if not token or not hmac.compare_digest(token.strip(), config.secret):
        raise HTTPException(status_code=401, detail="invalid CI token")


def _delivery_key(provider: str, payload: dict) -> str:
    if provider == "github":
        delivery = str(payload.get("delivery") or payload.get("hook_id") or "")
        after = payload.get("after") or ""
        return f"github:{delivery}:{after}"
    if provider == "gitlab":
        return f"gitlab:{payload.get('object_kind')}:{payload.get('project', {}).get('id')}:{payload.get('checkout_sha')}"
    return f"generic:{hashlib.sha256(str(payload).encode()).hexdigest()[:32]}"


def _parse_github_event(payload: dict, default_branch: str) -> tuple[str | None, int | None, list[str]]:
    kinds = ["unit", "api"]
    pr_obj = payload.get("pull_request")
    if isinstance(pr_obj, dict):
        base_ref = str((pr_obj.get("base") or {}).get("ref") or default_branch)
        if base_ref != default_branch:
            return None, None, []
        pr_number = pr_obj.get("number")
        return base_ref, int(pr_number) if pr_number else None, kinds

    ref = str(payload.get("ref") or "")
    branch = ref.split("/")[-1] if ref.startswith("refs/heads/") else ref
    if branch and branch != default_branch:
        return None, None, []
    return branch or default_branch, None, kinds


def trigger_run_from_webhook(
    db: Session,
    *,
    project: Project,
    config: CiWebhookConfig,
    payload: dict[str, Any],
    provider: str | None = None,
) -> dict[str, Any]:
    prov = (provider or config.provider or "generic").strip().lower()
    dkey = _delivery_key(prov, payload)
    existing = db.query(CiWebhookDelivery).filter(CiWebhookDelivery.delivery_key == dkey).one_or_none()
    if existing and existing.run_id:
        return {"duplicate": True, "run_id": existing.run_id, "delivery_key": dkey}

    branch = config.default_branch or "main"
    pr_number: int | None = None
    kinds = list(config.default_kinds or ["unit", "api"])
    if prov == "github":
        b, pr, k = _parse_github_event(payload, branch)
        if b is None:
            return {"skipped": True, "reason": f"branch mismatch (expected {branch})"}
        pr_number = pr
        kinds = k or kinds

    functional_ids = list_project_functional_case_ids(db, project_id=project.id)
    if functional_ids and "functional" not in kinds:
        kinds.append("functional")

    run = create_run_with_items(db, project_id=project.id, kinds=kinds)
    run_options = {
        "functional_case_ids": functional_ids,
        "ci": {
            "provider": prov,
            "delivery_key": dkey,
            "pr_number": pr_number,
            "github_repo": config.github_repo,
            "pr_comment_enabled": config.pr_comment_enabled,
        },
    }
    enqueue_test_run_job(db, run_id=run.id, command_overrides=None, run_options=run_options)

    delivery = existing or CiWebhookDelivery(
        project_id=project.id,
        delivery_key=dkey,
        provider=prov,
        ref=str(payload.get("ref") or branch),
        pr_number=pr_number,
        payload=payload,
    )
    delivery.run_id = run.id
    if not existing:
        db.add(delivery)
    db.commit()

    return {"run_id": run.id, "delivery_key": dkey, "kinds": kinds, "pr_number": pr_number}


def post_pr_comment_if_configured(db: Session, *, run: TestRun, project: Project) -> dict[str, Any]:
    run_row = run
    delivery = (
        db.query(CiWebhookDelivery)
        .filter(CiWebhookDelivery.run_id == run.id)
        .order_by(CiWebhookDelivery.id.desc())
        .first()
    )
    if not delivery or delivery.pr_comment_posted:
        return {"skipped": True}

    config = db.query(CiWebhookConfig).filter(CiWebhookConfig.project_id == project.id).one_or_none()
    if not config or not config.pr_comment_enabled or not config.github_token or not config.github_repo:
        return {"skipped": True, "reason": "github PR comment not configured"}

    pr_number = delivery.pr_number
    if not pr_number:
        return {"skipped": True, "reason": "no PR number"}

    owner, _, repo = config.github_repo.partition("/")
    if not owner or not repo:
        return {"skipped": True, "reason": "invalid github_repo"}

    summary_lines = [f"**AI-TP Run #{run.id}** — `{run.status}`"]
    for item in sorted(run_row.items, key=lambda x: x.id):
        summary_lines.append(f"- `{item.kind}`: **{item.status}**")
    body = "\n".join(summary_lines)

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(url, headers=headers, json={"body": body})
        if res.is_success:
            delivery.pr_comment_posted = True
            db.commit()
            return {"ok": True, "pr_number": pr_number}
        return {"ok": False, "status_code": res.status_code, "body": res.text[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
