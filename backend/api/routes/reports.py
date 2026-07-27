from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.api.auth import require_permission
from backend.api.deps import get_tenant_run
from backend.db.session import get_db
from backend.models.entities import Recipient, ReportArtifact, RunStatus, TestRun
from backend.schemas.dto import ReportEmailIn, ReportEmailOut, ReportOut
from backend.services.audit_service import log_action
from backend.services.notification import normalize_emails, send_report_email
from backend.services.report_service import build_html_report
from backend.services.smtp_config import resolve_smtp_config, smtp_public_view

router = APIRouter(tags=["reports"])


@router.get(
    "/reports/mail-status",
    dependencies=[Depends(require_permission("report.send"))],
)
def report_mail_status(db: Session = Depends(get_db)) -> dict:
    """SMTP / outbox readiness for the send-report UI."""
    return smtp_public_view(resolve_smtp_config(db))


@router.post("/runs/{run_id}/reports", response_model=ReportOut, dependencies=[Depends(require_permission("report.read"))])
def create_report(run: TestRun = Depends(get_tenant_run), db: Session = Depends(get_db)) -> ReportOut:
    if run.status in (RunStatus.pending.value, RunStatus.running.value):
        raise HTTPException(status_code=400, detail="run 仍在执行中，请稍后重试")

    report = build_html_report(db, run_id=run.id)
    preview = report.content if len(report.content) <= 500 else report.content[:500] + "…"
    return ReportOut(
        id=report.id,
        run_id=report.run_id,
        format=report.format,
        created_at=report.created_at,
        content_preview=preview,
    )


@router.get(
    "/runs/{run_id}/reports/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_permission("report.read"))],
)
def preview_report_html(run: TestRun = Depends(get_tenant_run), db: Session = Depends(get_db)) -> str:
    if run.status in (RunStatus.pending.value, RunStatus.running.value):
        raise HTTPException(status_code=400, detail="run 仍在执行中，请稍后重试")

    # Always rebuild so UI shows the latest detailed template (not a stale short artifact).
    report = build_html_report(db, run_id=run.id)
    return report.content


@router.post(
    "/runs/{run_id}/reports/send-email",
    response_model=ReportEmailOut,
    dependencies=[Depends(require_permission("report.send"))],
)
def send_report(
    body: ReportEmailIn | None = None,
    run: TestRun = Depends(get_tenant_run),
    db: Session = Depends(get_db),
) -> ReportEmailOut:
    if run.status in (RunStatus.pending.value, RunStatus.running.value):
        raise HTTPException(status_code=400, detail="run 仍在执行中，请稍后重试")

    report = build_html_report(db, run_id=run.id)

    project = run.project
    if not project:
        from backend.models.entities import Project

        project = db.query(Project).filter(Project.id == run.project_id).one()

    stored = db.query(Recipient).filter(Recipient.project_id == project.id).all()
    stored_emails = [r.email for r in stored]
    extra = [str(e) for e in (body.emails if body else [])]
    # Explicit emails from client = final recipient list; otherwise use project recipients.
    emails = normalize_emails(extra) if extra else normalize_emails(stored_emails)

    if not emails:
        return ReportEmailOut(
            ok=False,
            sent_to=[],
            report_id=report.id,
            skipped=True,
            reason="请先配置项目收件人，或在发送时填写临时邮箱",
        )

    if body and body.save_recipients and extra:
        existing = {e.lower() for e in stored_emails}
        for email in emails:
            if email in existing:
                continue
            db.add(Recipient(project_id=project.id, email=email, display_name=None))
            existing.add(email)
        db.commit()

    settings_smtp = resolve_smtp_config(db)
    if not settings_smtp.configured and not settings_smtp.dry_run:
        return ReportEmailOut(
            ok=False,
            sent_to=emails,
            report_id=report.id,
            skipped=True,
            mode="disabled",
            reason="未配置 SMTP，无法发送邮件。请前往「平台配置」填写 SMTP 主机。",
        )

    try:
        delivery = send_report_email(
            to_addresses=emails,
            subject=f"[测试报告] {project.name} - run #{run.id}",
            html_body=report.content,
            db=db,
            cfg=settings_smtp,
        )
    except RuntimeError as e:
        return ReportEmailOut(
            ok=False,
            sent_to=emails,
            report_id=report.id,
            skipped=True,
            mode="smtp" if settings_smtp.configured else "disabled",
            reason=str(e),
        )
    except Exception as e:  # noqa: BLE001
        from backend.services.notification import describe_smtp_error

        return ReportEmailOut(
            ok=False,
            sent_to=emails,
            report_id=report.id,
            skipped=True,
            mode="smtp",
            reason=describe_smtp_error(e, settings_smtp),
        )

    mode = str(delivery.get("mode") or "smtp")
    outbox_path = delivery.get("path")
    reason = None
    ok = True
    if mode == "outbox":
        # Soft success: content was saved locally, but not delivered to inbox.
        reason = (
            f"未配置 SMTP，报告未投递到邮箱，已写入本地发件箱：{outbox_path}。"
            "请在「平台配置 → 邮件 SMTP」填写主机后重试真实发送。"
        )

    log_action(
        db,
        module="reports",
        action="report.email_sent",
        message=f"report email sent for run #{run.id}",
        detail={
            "run_id": run.id,
            "project_id": project.id,
            "sent_to": emails,
            "mode": mode,
            "outbox_path": outbox_path,
        },
        organization_id=project.organization_id,
        project_id=project.id,
    )

    return ReportEmailOut(
        ok=ok,
        sent_to=emails,
        report_id=report.id,
        skipped=mode == "outbox",
        mode=mode,
        outbox_path=str(outbox_path) if outbox_path else None,
        reason=reason,
    )
