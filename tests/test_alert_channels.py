from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import get_settings
from backend.services.alert_channels import (
    dispatch_run_failure_alerts,
    send_dingtalk_markdown,
    send_wecom_markdown,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dingtalk_skipped_without_url(monkeypatch):
    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()
    result = send_dingtalk_markdown(title="t", text="body")
    assert result.get("skipped") is True


@patch("backend.services.alert_channels.httpx.Client")
def test_dingtalk_post_success(mock_client_cls, monkeypatch):
    monkeypatch.setenv("DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=test")
    monkeypatch.setenv("DINGTALK_WEBHOOK_SECRET", "")
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = send_dingtalk_markdown(title="失败", text="### 详情")
    assert result["ok"] is True
    assert result["channel"] == "dingtalk"


@patch("backend.services.alert_channels.httpx.Client")
def test_wecom_post_success(mock_client_cls, monkeypatch):
    monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.text = '{"errcode":0}'
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = send_wecom_markdown(content="### Run failed")
    assert result["ok"] is True
    assert result["channel"] == "wecom"


@patch("backend.services.alert_channels.send_generic_webhook")
@patch("backend.services.alert_channels.send_dingtalk_markdown")
def test_dispatch_channels(mock_ding, mock_generic, monkeypatch):
    monkeypatch.setenv("RUN_FAILURE_ALERT_CHANNELS", "generic,dingtalk")
    monkeypatch.setenv("RUN_FAILURE_WEBHOOK_URL", "https://hooks.example.com/run")
    get_settings.cache_clear()

    mock_generic.return_value = {"ok": True}
    mock_ding.return_value = {"ok": True, "channel": "dingtalk"}

    out = dispatch_run_failure_alerts(
        project_name="Demo",
        run_id=1,
        job_id=2,
        attempts=3,
        status="failed",
        last_error="timeout",
    )
    assert "generic" in out
    assert "dingtalk" in out
    mock_generic.assert_called_once()
    mock_ding.assert_called_once()
