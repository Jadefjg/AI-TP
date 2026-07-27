from __future__ import annotations

from fastapi.testclient import TestClient

from backend.services.login_crypto_service import encrypt_change_password_for_tests
from tests.auth_helpers import login_with_encrypted_password


def test_change_password_returns_new_token(client: TestClient):
    login = login_with_encrypted_password(client, username="admin", password="admin123456")
    assert login.status_code == 200, login.text
    old_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {old_token}"}

    challenge = client.get("/auth/login-challenge")
    assert challenge.status_code == 200, challenge.text
    payload = challenge.json()
    encrypted_payload = encrypt_change_password_for_tests(
        payload["challenge_id"],
        "admin123456",
        "admin1234567",
        payload["public_key"],
    )
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"challenge_id": payload["challenge_id"], "encrypted_payload": encrypted_payload},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["access_token"] != old_token
    assert body["user"]["username"] == "admin"

    new_headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/auth/me", headers=new_headers)
    assert me.status_code == 200

    stale = client.get("/auth/me", headers=headers)
    assert stale.status_code == 401

    revert_challenge = client.get("/auth/login-challenge")
    revert_payload = revert_challenge.json()
    revert_encrypted = encrypt_change_password_for_tests(
        revert_payload["challenge_id"],
        "admin1234567",
        "admin123456",
        revert_payload["public_key"],
    )
    reverted = client.post(
        "/auth/change-password",
        headers=new_headers,
        json={
            "challenge_id": revert_payload["challenge_id"],
            "encrypted_payload": revert_encrypted,
        },
    )
    assert reverted.status_code == 200, reverted.text
