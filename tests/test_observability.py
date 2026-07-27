from __future__ import annotations


def test_metrics_endpoint(client):
    """Default test env: METRICS_AUTH_ENABLED=false (see test_metrics_auth.py)."""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "ai_tp_http_requests_total" in res.text


def test_request_trace_headers(client):
    res = client.get("/", headers={"X-Request-ID": "req-test-1"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == "req-test-1"
    assert res.headers.get("X-Trace-ID")
