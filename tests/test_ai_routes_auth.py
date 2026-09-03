from __future__ import annotations

from fastapi.testclient import TestClient

from tests.auth_helpers import login_with_encrypted_password
from tests.project_helpers import create_test_project


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    return create_test_project(client, headers, name="ai-auth-test")


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
    login = login_with_encrypted_password(client, username="admin", password="admin123")
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
