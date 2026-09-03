from __future__ import annotations

from fastapi.testclient import TestClient


def test_ops_overview(client: TestClient, admin_headers: dict):
    res = client.get("/ops/overview", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "health_score" in body
    assert "queue" in body
    assert "scheduled_jobs" in body
    assert "alert_channels" in body


def test_ops_dictionaries_seed_and_list(client: TestClient, admin_headers: dict):
    seed = client.post("/ops/dictionaries/seed", headers=admin_headers)
    assert seed.status_code == 200, seed.text
    listed = client.get("/ops/dictionaries", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    codes = {row["code"] for row in listed.json()}
    assert codes


def test_ops_schedule_whitelist_and_run(client: TestClient, admin_headers: dict):
    handlers = client.get("/ops/schedule/handlers", headers=admin_headers)
    assert handlers.status_code == 200, handlers.text
    keys = {row["key"] for row in handlers.json()}
    assert "ops.health_snapshot" in keys

    bad = client.post(
        "/ops/schedule/jobs",
        headers=admin_headers,
        json={
            "name": "evil-shell",
            "handler_key": "shell.exec",
            "interval_seconds": 3600,
            "enabled": True,
        },
    )
    assert bad.status_code == 400, bad.text

    seed = client.post("/ops/schedule/seed", headers=admin_headers)
    assert seed.status_code == 200, seed.text
    jobs = client.get("/ops/schedule/jobs", headers=admin_headers)
    assert jobs.status_code == 200, jobs.text
    assert jobs.json()
    job_id = jobs.json()[0]["id"]
    run = client.post(f"/ops/schedule/jobs/{job_id}/run", headers=admin_headers)
    assert run.status_code == 200, run.text
    assert run.json()["status"] in {"completed", "failed", "skipped"}


def test_setting_revision_and_rollback(client: TestClient, admin_headers: dict):
    key = "ops.test.rollback.flag"
    create = client.post(
        "/settings",
        headers=admin_headers,
        json={"key": key, "value": "v1", "description": "ops test"},
    )
    assert create.status_code == 200, create.text
    update = client.post(
        "/settings",
        headers=admin_headers,
        json={"key": key, "value": "v2", "description": "ops test"},
    )
    assert update.status_code == 200, update.text
    revs = client.get(f"/settings/revisions?key={key}", headers=admin_headers)
    assert revs.status_code == 200, revs.text
    assert len(revs.json()) >= 2
    latest_update = next(row for row in revs.json() if row["change_type"] == "update")
    rollback = client.post(f"/settings/revisions/{latest_update['id']}/rollback", headers=admin_headers)
    assert rollback.status_code == 200, rollback.text
    listed = client.get("/settings", headers=admin_headers)
    assert listed.status_code == 200
    hit = next(row for row in listed.json() if row["key"] == key)
    assert hit["value"] == "v1"
