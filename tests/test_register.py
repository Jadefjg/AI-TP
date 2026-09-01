from __future__ import annotations

from fastapi.testclient import TestClient

from backend.services.login_crypto_service import encrypt_login_password_for_tests
from tests.auth_helpers import login_with_encrypted_password


def _register_with_encrypted_password(
    client: TestClient,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    email: str | None = None,
):
    challenge = client.get("/auth/login-challenge")
    assert challenge.status_code == 200, challenge.text
    payload = challenge.json()
    encrypted_password = encrypt_login_password_for_tests(
        payload["challenge_id"],
        password,
        payload["public_key"],
    )
    body = {
        "username": username,
        "challenge_id": payload["challenge_id"],
        "encrypted_password": encrypted_password,
    }
    if display_name is not None:
        body["display_name"] = display_name
    if email is not None:
        body["email"] = email
    return client.post("/auth/register", json=body)


def test_register_and_login(client: TestClient):
    username = "test_user_register"
    password = "testpass123"

    register_res = _register_with_encrypted_password(
        client,
        username=username,
        password=password,
        display_name="Test User",
    )
    assert register_res.status_code == 200, register_res.text
    body = register_res.json()
    assert body["access_token"]
    assert body["user"]["username"] == username
    assert any(role["name"] == "member" for role in body["user"]["roles"])

    login_res = login_with_encrypted_password(client, username=username, password=password)
    assert login_res.status_code == 200, login_res.text


def test_register_duplicate_username(client: TestClient):
    username = "dup_user_test"
    password = "testpass123"

    first = _register_with_encrypted_password(client, username=username, password=password)
    assert first.status_code == 200, first.text

    second = _register_with_encrypted_password(client, username=username, password=password)
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]
