from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import Project, Recipient, TestRun
from backend.services.alert_channels import dispatch_run_failure_alerts
from backend.services.audit_service import log_action
from backend.services.notification import send_report_email
from backend.services.smtp_config import resolve_smtp_config

logger = logging.getLogger(__name__)


def notify_run_failure(
    db: Session,
    *,
    run: TestRun,
    project: Project | None,
    job_id: int,
    last_error: str | None,
    attempts: int,
) -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {"email": None, "channels": {}}

    if not settings.run_failure_alert_enabled:
        return result

    project = project or db.query(Project).filter(Project.id == run.project_id).one_or_none()
    project_name = project.name if project else f"project #{run.project_id}"
    subject = f"[测试失败] {project_name} — Run #{run.id}"
    body = (
        f"<p>Run <b>#{run.id}</b> 执行失败（任务 #{job_id}，尝试 {attempts} 次）。</p>"
        f"<p>状态：<code>{run.status}</code></p>"
        f"<p>错误：<pre>{last_error or run.error_message or '—'}</pre></p>"
        f"<p>请在任务中心或 Run 详情页查看完整日志。</p>"
    )

    cfg = resolve_smtp_config(db)
    if cfg.configured and project:
        emails = [r.email for r in db.query(Recipient).filter(Recipient.project_id == project.id).all()]
        if emails:
            try:
                send_report_email(to_addresses=emails, subject=subject, html_body=body, db=db, cfg=cfg)
                result["email"] = {"ok": True, "sent_to": emails}
                log_action(
                    db,
                    module="alerts",
                    action="run.failure_email_sent",
                    message=f"failure alert email for run #{run.id}",
                    detail={"run_id": run.id, "job_id": job_id, "sent_to": emails},
                )
            except Exception as exc:  # noqa: BLE001
                result["email"] = {"ok": False, "error": str(exc)}
                logger.warning("run failure email failed: %s", exc)

    try:
        result["channels"] = dispatch_run_failure_alerts(
            project_name=project_name,
            run_id=run.id,
            job_id=job_id,
            attempts=attempts,
            status=run.status,
            last_error=last_error or run.error_message,
        )
        log_action(
            db,
            module="alerts",
            action="run.failure_channels",
            message=f"alert channels dispatched for run #{run.id}",
            detail={"run_id": run.id, "channels": result["channels"]},
        )
    except Exception as exc:  # noqa: BLE001
        result["channels"] = {"error": str(exc)}
        logger.warning("run failure channel dispatch failed: %s", exc)

    return result
