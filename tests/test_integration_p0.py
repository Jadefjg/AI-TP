from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.entities import ExecutionJob, Permission, Role, RunStatus, User
from backend.models.entities import TestRun as TestRunRow
from backend.services.auth_service import hash_password
from backend.services.job_queue import process_job
from tests.auth_helpers import login_with_encrypted_password


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/projects",
        headers=headers,
        json={"name": "p0-test", "code_root": ".", "repo_source": "local"},
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_case_crud_forbidden_without_write(client: TestClient, db: Session, admin_headers: dict[str, str]):
    viewer_role = Role(name="viewer-p0", description="read only cases")
    db.add(viewer_role)
    db.flush()
    read_perm = db.query(Permission).filter(Permission.code == "case.read").one()
    viewer_role.permissions = [read_perm]
    viewer = User(
        username="viewer_p0",
        display_name="Viewer",
        password_hash=hash_password("viewer123456"),
        is_active=True,
        roles=[viewer_role],
    )
    db.add(viewer)
    db.commit()

    login = login_with_encrypted_password(client, username="viewer_p0", password="viewer123456")
    assert login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    project_id = _create_project(client, admin_headers)
    denied = client.post(
        f"/projects/{project_id}/functional-cases",
        headers=viewer_headers,
        json={"title": "x", "steps": ["s1"]},
    )
    assert denied.status_code == 403
    assert "case.write" in denied.json()["detail"]


def test_case_crud_happy_path(client: TestClient, admin_headers: dict[str, str]):
    project_id = _create_project(client, admin_headers)
    created = client.post(
        f"/projects/{project_id}/functional-cases",
        headers=admin_headers,
        json={"title": "login", "steps": ["open app", "submit"], "priority": "high"},
    )
    assert created.status_code == 200
    case_id = created.json()["id"]

    listed = client.get(f"/projects/{project_id}/functional-cases", headers=admin_headers)
    assert listed.status_code == 200
    assert any(c["id"] == case_id for c in listed.json())

    updated = client.patch(
        f"/projects/{project_id}/functional-cases/{case_id}",
        headers=admin_headers,
        json={"title": "login updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "login updated"

    deleted = client.delete(f"/projects/{project_id}/functional-cases/{case_id}", headers=admin_headers)
    assert deleted.status_code == 200


@patch("backend.services.orchestrator.execute_run")
def test_start_run_enqueues_job_and_executes(mock_execute, client: TestClient, db: Session, admin_headers: dict[str, str]):
    def _fake_execute(db_sess, run, project, overrides, run_options=None, job_id=None):
        for item in run.items:
            item.status = "skipped"
            item.detail = {"reason": "integration mock", "api_mode": run_options}
        run.status = "completed"
        db_sess.commit()

    mock_execute.side_effect = _fake_execute

    project_id = _create_project(client, admin_headers)
    res = client.post(
        f"/projects/{project_id}/runs",
        headers=admin_headers,
        json={"kinds": ["api"], "api_mode": "dsl"},
    )
    assert res.status_code == 202, res.text
    run_id = res.json()["id"]
    assert res.json()["execution_job"] is not None
    assert res.json()["execution_job"]["status"] == "pending"

    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one()
    process_job(db, job.id)
    db.expire_all()

    detail = client.get(f"/runs/{run_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] in {"completed", "failed"}
    assert body["items"][0]["kind"] == "api"
    mock_execute.assert_called_once()


@patch("backend.services.orchestrator.execute_project_perf_k6")
def test_start_run_perf_k6(mock_k6, client: TestClient, db: Session, admin_headers: dict[str, str]):
    mock_k6.return_value = {
        "command_label": "k6://mock",
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "status": "passed",
        "detail": {"engine": "k6", "mock": True},
    }

    project_id = _create_project(client, admin_headers)
    res = client.post(
        f"/projects/{project_id}/runs",
        headers=admin_headers,
        json={"kinds": ["perf_backend"], "perf_mode": "k6"},
    )
    assert res.status_code == 202
    run_id = res.json()["id"]
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one()
    process_job(db, job.id)
    mock_k6.assert_called_once()
    detail = client.get(f"/runs/{run_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["items"][0]["kind"] == "perf_backend"
    assert detail.json()["items"][0]["detail"].get("mock") is True


@patch("backend.services.orchestrator.execute_integrated_security")
def test_start_run_security_combined(mock_sec, client: TestClient, db: Session, admin_headers: dict[str, str]):
    mock_sec.return_value = {
        "command_label": "security://combined",
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "status": "passed",
        "detail": {"engine": "builtin", "findings": []},
    }

    project_id = _create_project(client, admin_headers)
    res = client.post(
        f"/projects/{project_id}/runs",
        headers=admin_headers,
        json={
            "kinds": ["sec_backend"],
            "security_mode": "combined",
            "security_target_url": "http://127.0.0.1:8001",
        },
    )
    assert res.status_code == 202
    run_id = res.json()["id"]
    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == run_id).one()
    process_job(db, job.id)
    mock_sec.assert_called_once()
    detail = client.get(f"/runs/{run_id}", headers=admin_headers)
    assert detail.json()["items"][0]["kind"] == "sec_backend"


def test_cancel_pending_run(client: TestClient, admin_headers: dict[str, str]):
    project_id = _create_project(client, admin_headers)
    res = client.post(f"/projects/{project_id}/runs", headers=admin_headers, json={"kinds": ["unit"]})
    assert res.status_code == 202
    run_id = res.json()["id"]

    cancelled = client.post(f"/runs/{run_id}/cancel", headers=admin_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    run = client.get(f"/runs/{run_id}", headers=admin_headers)
    assert run.json()["status"] == "cancelled"


def test_report_html_and_email_feedback(client: TestClient, db: Session, admin_headers: dict[str, str]):
    project_id = _create_project(client, admin_headers)
    res = client.post(f"/projects/{project_id}/runs", headers=admin_headers, json={"kinds": ["unit"]})
    run_id = res.json()["id"]

    run = db.query(TestRunRow).filter(TestRunRow.id == run_id).one()
    run.status = RunStatus.completed.value
    db.commit()

    report = client.post(f"/runs/{run_id}/reports", headers=admin_headers)
    assert report.status_code == 200

    html = client.get(f"/runs/{run_id}/reports/html", headers=admin_headers)
    assert html.status_code == 200
    assert "<html" in html.text.lower() or "<table" in html.text.lower()

    client.post(
        f"/projects/{project_id}/recipients",
        headers=admin_headers,
        json={"email": "qa@example.com", "display_name": "QA"},
    )
    mail = client.post(f"/runs/{run_id}/reports/send-email", headers=admin_headers)
    assert mail.status_code == 200
    body = mail.json()
    assert body["ok"] is True
    assert "qa@example.com" in body["sent_to"]
    assert body.get("mode") in ("outbox", "smtp")
