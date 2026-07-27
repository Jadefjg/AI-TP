from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        res = client.post(url, json=payload)
    return {"ok": res.is_success, "status_code": res.status_code, "body": res.text[:500]}


def send_generic_webhook(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post_json(url, payload)


def _dingtalk_signed_url(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    ts = str(round(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}"
    sign = urllib.parse.quote_plus(
        base64.b64encode(hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest())
    )
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={ts}&sign={sign}"


def send_dingtalk_markdown(*, title: str, text: str) -> dict[str, Any]:
    settings = get_settings()
    webhook = (settings.dingtalk_webhook_url or "").strip()
    if not webhook:
        return {"ok": False, "skipped": True, "reason": "DINGTALK_WEBHOOK_URL not set"}
    url = _dingtalk_signed_url(webhook, (settings.dingtalk_webhook_secret or "").strip())
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title[:128], "text": text[:18000]},
    }
    try:
        result = _post_json(url, payload)
        if result.get("ok"):
            return {"ok": True, "channel": "dingtalk"}
        return {"ok": False, "channel": "dingtalk", **result}
    except Exception as exc:  # noqa: BLE001
        logger.warning("dingtalk alert failed: %s", exc)
        return {"ok": False, "channel": "dingtalk", "error": str(exc)}


def send_wecom_markdown(*, content: str) -> dict[str, Any]:
    settings = get_settings()
    webhook = (settings.wecom_webhook_url or "").strip()
    if not webhook:
        return {"ok": False, "skipped": True, "reason": "WECOM_WEBHOOK_URL not set"}
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content[:18000]},
    }
    try:
        result = _post_json(webhook, payload)
        if result.get("ok"):
            return {"ok": True, "channel": "wecom"}
        return {"ok": False, "channel": "wecom", **result}
    except Exception as exc:  # noqa: BLE001
        logger.warning("wecom alert failed: %s", exc)
        return {"ok": False, "channel": "wecom", "error": str(exc)}


def format_run_failure_markdown(
    *,
    project_name: str,
    run_id: int,
    job_id: int,
    attempts: int,
    status: str,
    last_error: str | None,
) -> tuple[str, str]:
    title = f"测试失败 · {project_name} · Run #{run_id}"
    text = (
        f"### {title}\n\n"
        f"- **项目**: {project_name}\n"
        f"- **Run**: #{run_id}\n"
        f"- **任务**: #{job_id}\n"
        f"- **尝试次数**: {attempts}\n"
        f"- **状态**: `{status}`\n"
        f"- **错误**: \n\n```\n{(last_error or '—')[:2000]}\n```\n\n"
        f"> 请登录平台任务中心或 Run 详情查看完整日志。"
    )
    return title, text


def dispatch_run_failure_alerts(
    *,
    project_name: str,
    run_id: int,
    job_id: int,
    attempts: int,
    status: str,
    last_error: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    channels = {c.strip().lower() for c in (settings.run_failure_alert_channels or "generic").split(",") if c.strip()}
    title, md_text = format_run_failure_markdown(
        project_name=project_name,
        run_id=run_id,
        job_id=job_id,
        attempts=attempts,
        status=status,
        last_error=last_error,
    )
    out: dict[str, Any] = {}

    if "generic" in channels and (settings.run_failure_webhook_url or "").strip():
        out["generic"] = send_generic_webhook(
            settings.run_failure_webhook_url.strip(),
            {
                "event": "run.failed",
                "run_id": run_id,
                "job_id": job_id,
                "project_name": project_name,
                "attempts": attempts,
                "last_error": last_error,
                "status": status,
            },
        )

    if "dingtalk" in channels:
        out["dingtalk"] = send_dingtalk_markdown(title=title, text=md_text)

    if "wecom" in channels:
        out["wecom"] = send_wecom_markdown(content=md_text)

    return out
