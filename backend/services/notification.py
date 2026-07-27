from __future__ import annotations

import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from sqlalchemy.orm import Session

from backend.services.smtp_config import SmtpRuntimeConfig, resolve_smtp_config, validate_smtp_ready

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLACEHOLDER_FROM = {"noreply@example.com", "no-reply@example.com"}


def normalize_emails(emails: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in emails or []:
        email = (raw or "").strip().lower()
        if not email or email in seen:
            continue
        if not _EMAIL_RE.match(email):
            continue
        seen.add(email)
        out.append(email)
    return out


def _write_outbox(
    *,
    cfg: SmtpRuntimeConfig,
    to_addresses: list[str],
    subject: str,
    html_body: str,
) -> Path:
    root = Path(cfg.outbox_dir or "./data/mail_outbox")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_subject = re.sub(r"[^\w\-]+", "_", subject)[:48] or "report"
    path = root / f"{stamp}_{safe_subject}.eml.html"
    header = (
        f"<!-- dry-run outbox -->\n"
        f"<!-- From: {cfg.from_addr} -->\n"
        f"<!-- To: {', '.join(to_addresses)} -->\n"
        f"<!-- Subject: {subject} -->\n"
    )
    path.write_text(header + html_body, encoding="utf-8")
    return path


def describe_smtp_error(exc: BaseException, cfg: SmtpRuntimeConfig) -> str:
    raw = str(exc).strip() or exc.__class__.__name__
    lower = raw.lower()
    host = cfg.host.strip().lower()

    if "connection unexpectedly closed" in lower or "connection reset" in lower:
        tips = [
            "SMTP 连接被服务器断开，常见原因：",
            "1) 用户名应填完整邮箱（不是 admin）；",
            "2) 密码应填邮箱授权码（不是登录密码）；",
            "3) From 需与发件邮箱一致；",
            "4) QQ 邮箱建议端口 465 + SSL，或 587 + STARTTLS（不要混用）。",
        ]
        if "qq.com" in host:
            tips.append("当前主机为 smtp.qq.com，请按 QQ 邮箱 SMTP 要求检查授权码与端口。")
        return " ".join(tips) + f" 原始错误：{raw}"

    if isinstance(exc, smtplib.SMTPAuthenticationError) or "auth" in lower or "535" in lower:
        return (
            "SMTP 认证失败：请确认用户名为完整邮箱，密码为授权码（QQ/163 等不是网页登录密码）。"
            f" 原始错误：{raw}"
        )
    if isinstance(exc, smtplib.SMTPSenderRefused) or "sender" in lower or "553" in lower:
        return (
            "发件人被拒绝：请将 From 设置为与 SMTP 用户名相同的邮箱地址。"
            f" 原始错误：{raw}"
        )
    if "timed out" in lower or "timeout" in lower:
        return f"连接 SMTP 超时，请检查主机/端口/防火墙。原始错误：{raw}"
    if "ssl" in lower or "certificate" in lower:
        return (
            "SSL/TLS 握手失败：QQ 邮箱请使用 465+SSL 或 587+STARTTLS，不要同时开启两者。"
            f" 原始错误：{raw}"
        )
    return f"邮件发送失败：{raw}"


def _normalized_transport(cfg: SmtpRuntimeConfig) -> tuple[bool, bool]:
    """Resolve SSL vs STARTTLS from flags and port. Prefer SSL on 465, STARTTLS on 587."""
    use_ssl = bool(cfg.use_ssl)
    use_tls = bool(cfg.use_tls)
    if cfg.port == 465:
        return True, False
    if cfg.port == 587:
        return False, True
    if use_ssl and use_tls:
        # Avoid double wrap; prefer explicit SSL when both checked.
        return True, False
    return use_ssl, use_tls


def _effective_from(cfg: SmtpRuntimeConfig) -> str:
    user = (cfg.user or "").strip()
    from_addr = (cfg.from_addr or "").strip()
    if (not from_addr or from_addr.lower() in _PLACEHOLDER_FROM) and _EMAIL_RE.match(user.lower()):
        return user
    return from_addr or user or "noreply@example.com"


def _send_via_smtp(cfg: SmtpRuntimeConfig, addresses: list[str], subject: str, html_body: str) -> None:
    ready_hint = validate_smtp_ready(cfg)
    if ready_hint:
        raise RuntimeError(ready_hint)

    from_addr = _effective_from(cfg)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("", from_addr))
    msg["To"] = ", ".join(addresses)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    payload = msg.as_string()

    use_ssl, use_tls = _normalized_transport(cfg)
    context = ssl.create_default_context()
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=60, context=context) as server:
                server.ehlo()
                if cfg.user:
                    server.login(cfg.user.strip(), cfg.password)
                server.sendmail(from_addr, addresses, payload)
            return

        with smtplib.SMTP(cfg.host, cfg.port, timeout=60) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=context)
                server.ehlo()
            if cfg.user:
                server.login(cfg.user.strip(), cfg.password)
            server.sendmail(from_addr, addresses, payload)
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(describe_smtp_error(exc, cfg)) from exc


def send_report_email(
    to_addresses: list[str],
    subject: str,
    html_body: str,
    *,
    db: Session | None = None,
    cfg: SmtpRuntimeConfig | None = None,
) -> dict:
    """Send report email via SMTP, or write a local outbox file when dry-run is enabled.

    Returns:
        {"mode": "smtp"|"outbox", "sent_to": [...], "path": optional outbox path}
    """
    addresses = normalize_emails(to_addresses)
    if not addresses:
        raise RuntimeError("收件人列表为空")

    runtime = cfg or resolve_smtp_config(db)
    if runtime.host:
        _send_via_smtp(runtime, addresses, subject, html_body)
        return {"mode": "smtp", "sent_to": addresses}

    if runtime.dry_run:
        path = _write_outbox(
            cfg=runtime,
            to_addresses=addresses,
            subject=subject,
            html_body=html_body,
        )
        return {"mode": "outbox", "sent_to": addresses, "path": str(path)}

    raise RuntimeError("未配置 SMTP，无法发送邮件。请在「平台配置」填写 SMTP，或设置 SMTP_HOST。")
