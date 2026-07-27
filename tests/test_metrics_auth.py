from __future__ import annotations

import pytest

from backend.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_metrics_open_when_auth_disabled(client, monkeypatch):
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "ai_tp_http_requests_total" in res.text


def test_metrics_requires_bearer_when_enabled(client, monkeypatch):
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "scrape-secret-token")
    get_settings.cache_clear()

    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-Metrics-Token": "wrong"}).status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret-token"})
    assert ok.status_code == 200


def test_metrics_jwt_system_read_fallback(client, admin_headers, monkeypatch):
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "")
    get_settings.cache_clear()

    assert client.get("/metrics").status_code == 401
    res = client.get("/metrics", headers=admin_headers)
    assert res.status_code == 200
