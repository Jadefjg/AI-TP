"""Project lifecycle API."""


def test_update_project(client, admin_headers):
    create = client.post(
        "/projects",
        headers=admin_headers,
        json={
            "name": "To Update",
            "code_root": "https://example.com/app",
            "repo_source": "deployed",
            "description": "before",
        },
    )
    assert create.status_code == 200, create.text
    pid = create.json()["id"]

    updated = client.patch(
        f"/projects/{pid}",
        headers=admin_headers,
        json={
            "name": "UGC",
            "code_root": "https://funhub-web-test.guadd.fun",
            "repo_source": "deployed",
            "description": "至性能测试",
            "repo_branch": None,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "UGC"
    assert body["code_root"] == "https://funhub-web-test.guadd.fun"
    assert body["description"] == "至性能测试"
    assert body["repo_source"] == "deployed"


def test_delete_project(client, admin_headers):
    create = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "To Delete", "code_root": "/tmp/to-delete"},
    )
    assert create.status_code == 200
    pid = create.json()["id"]

    listed = client.get("/projects", headers=admin_headers)
    assert any(row["id"] == pid for row in listed.json())

    deleted = client.delete(f"/projects/{pid}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "project_id": pid}

    assert client.get(f"/projects/{pid}", headers=admin_headers).status_code == 404
    assert not any(row["id"] == pid for row in client.get("/projects", headers=admin_headers).json())


def test_delete_project_not_found(client, admin_headers):
    resp = client.delete("/projects/999999", headers=admin_headers)
    assert resp.status_code == 404
