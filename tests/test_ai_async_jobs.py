"""Smoke tests for project base_url and async AI jobs."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _create_project(client: TestClient, headers: dict[str, str], **extra) -> dict:
    body = {
        "name": "BaseURL Project",
        "code_root": "/tmp/ai-tp-demo",
        "repo_source": "local",
        "repo_branch": "main",
        **extra,
    }
    resp = client.post("/projects", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_project_base_url_persisted(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = _create_project(client, admin_headers, base_url="https://sut.example.com/api/")
    assert created["base_url"] == "https://sut.example.com/api"

    project_id = created["id"]
    got = client.get(f"/projects/{project_id}", headers=admin_headers)
    assert got.status_code == 200
    assert got.json()["base_url"] == "https://sut.example.com/api"

    patched = client.patch(
        f"/projects/{project_id}",
        json={
            "name": created["name"],
            "description": None,
            "code_root": created["code_root"],
            "repo_source": "local",
            "repo_branch": "main",
            "base_url": "http://127.0.0.1:9000",
        },
        headers=admin_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["base_url"] == "http://127.0.0.1:9000"


def test_ai_job_enqueue_and_complete(client: TestClient, admin_headers: dict[str, str]) -> None:
    project = _create_project(client, admin_headers)
    project_id = project["id"]

    enq = client.post(
        f"/projects/{project_id}/ai/jobs",
        json={
            "module_type": "functional_cases",
            "requirement_text": "用户可以登录并查看个人资料。",
            "openapi_content": "",
        },
        headers=admin_headers,
    )
    assert enq.status_code == 202, enq.text
    job = enq.json()
    assert job["status"] in {"pending", "running", "completed", "failed"}
    job_id = job["id"]

    deadline = time.time() + 60
    final = None
    while time.time() < deadline:
        poll = client.get(f"/projects/{project_id}/ai/jobs/{job_id}", headers=admin_headers)
        assert poll.status_code == 200, poll.text
        final = poll.json()
        if final["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.5)

    assert final is not None
    assert final["status"] == "completed", final
    assert isinstance(final.get("result_payload"), dict)
    assert final["result_payload"].get("module_type") == "functional_cases"
