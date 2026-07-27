"""Report email send + local outbox dry-run."""

from pathlib import Path

from backend.services.notification import describe_smtp_error, normalize_emails, send_report_email
from backend.services.smtp_config import SmtpRuntimeConfig, validate_smtp_ready


def test_normalize_emails_dedupes_and_filters():
    assert normalize_emails(["QA@Example.COM", "qa@example.com", "not-an-email", ""]) == [
        "qa@example.com"
    ]


def test_validate_smtp_ready_rejects_non_email_user():
    cfg = SmtpRuntimeConfig(
        host="smtp.qq.com",
        port=465,
        user="admin",
        password="auth-code",
        use_tls=False,
        use_ssl=True,
        from_addr="noreply@example.com",
        dry_run=True,
        outbox_dir="./data/mail_outbox",
    )
    hint = validate_smtp_ready(cfg)
    assert hint is not None
    assert "不是邮箱地址" in hint


def test_describe_smtp_error_connection_closed():
    cfg = SmtpRuntimeConfig(
        host="smtp.qq.com",
        port=465,
        user="admin",
        password="x",
        use_tls=False,
        use_ssl=True,
        from_addr="noreply@example.com",
        dry_run=True,
        outbox_dir="./data/mail_outbox",
    )
    msg = describe_smtp_error(RuntimeError("Connection unexpectedly closed"), cfg)
    assert "完整邮箱" in msg
    assert "授权码" in msg


def test_send_report_email_writes_outbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("SMTP_DRY_RUN", "true")
    monkeypatch.setenv("SMTP_OUTBOX_DIR", str(tmp_path))
    from backend.core.config import get_settings

    get_settings.cache_clear()
    cfg = SmtpRuntimeConfig(
        host="",
        port=587,
        user="",
        password="",
        use_tls=True,
        use_ssl=False,
        from_addr="noreply@example.com",
        dry_run=True,
        outbox_dir=str(tmp_path),
    )
    result = send_report_email(
        to_addresses=["qa@example.com"],
        subject="[测试报告] unit",
        html_body="<html><body>hello</body></html>",
        cfg=cfg,
    )
    assert result["mode"] == "outbox"
    assert result["sent_to"] == ["qa@example.com"]
    path = Path(result["path"])
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "qa@example.com" in text
    assert "hello" in text
    get_settings.cache_clear()


def test_send_report_email_blocks_bad_qq_config(tmp_path):
    cfg = SmtpRuntimeConfig(
        host="smtp.qq.com",
        port=465,
        user="admin",
        password="secret",
        use_tls=False,
        use_ssl=True,
        from_addr="noreply@example.com",
        dry_run=False,
        outbox_dir=str(tmp_path),
    )
    try:
        send_report_email(
            to_addresses=["qa@example.com"],
            subject="bad cfg",
            html_body="<p>x</p>",
            cfg=cfg,
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "不是邮箱地址" in str(exc)
