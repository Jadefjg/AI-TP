from __future__ import annotations

from fastapi.testclient import TestClient

from tests.auth_helpers import login_with_encrypted_password


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/projects",
        headers=headers,
        json={"name": "ai-auth-test", "code_root": ".", "repo_source": "local"},
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_project_ai_list_routes_require_bearer_token(client: TestClient, admin_headers: dict[str, str]):
    project_id = _create_project(client, admin_headers)
    paths = [
        f"/projects/{project_id}/ai/artifacts",
        f"/projects/{project_id}/ai/requirement-reviews",
        f"/projects/{project_id}/ai/security-scan-jobs",
    ]
    for path in paths:
        denied = client.get(path)
        assert denied.status_code == 401, path
        assert denied.json()["detail"] == "authentication required"


def test_project_ai_list_routes_accept_valid_token(client: TestClient):
    login = login_with_encrypted_password(client, username="admin", password="admin123456")
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    project_id = _create_project(client, headers)
    paths = [
        f"/projects/{project_id}/ai/artifacts",
        f"/projects/{project_id}/ai/requirement-reviews",
        f"/projects/{project_id}/ai/security-scan-jobs",
    ]
    for path in paths:
        res = client.get(path, headers=headers)
        assert res.status_code == 200, f"{path}: {res.text}"
