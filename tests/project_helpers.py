from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def create_test_project(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str = "test-project",
    code_root: str | None = None,
    repo_source: str = "local",
) -> int:
    """Create a project with an absolute local path (required by project validation)."""
    root = code_root or str(Path.cwd())
    res = client.post(
        "/projects",
        headers=headers,
        json={"name": name, "code_root": root, "repo_source": repo_source},
    )
    assert res.status_code == 200, res.text
    return int(res.json()["id"])
