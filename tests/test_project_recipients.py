"""Project report email recipients API."""


def test_list_and_delete_recipients(client, admin_headers, db):
    create = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "Recipients", "code_root": "/tmp/recipients"},
    )
    assert create.status_code == 200
    pid = create.json()["id"]

    add = client.post(
        f"/projects/{pid}/recipients",
        headers=admin_headers,
        json={"email": "qa@example.com", "display_name": "QA"},
    )
    assert add.status_code == 200
    rid = add.json()["id"]
    assert add.json()["email"] == "qa@example.com"

    listed = client.get(f"/projects/{pid}/recipients", headers=admin_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["display_name"] == "QA"

    deleted = client.delete(f"/projects/{pid}/recipients/{rid}", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get(f"/projects/{pid}/recipients", headers=admin_headers).json() == []
