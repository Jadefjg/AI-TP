from __future__ import annotations

from fastapi.testclient import TestClient

from backend.services.login_crypto_service import encrypt_login_password_for_tests


def login_with_encrypted_password(
    client: TestClient,
    *,
    username: str,
    password: str,
) -> TestClient:
    challenge = client.get("/auth/login-challenge")
    assert challenge.status_code == 200, challenge.text
    payload = challenge.json()
    encrypted_password = encrypt_login_password_for_tests(
        payload["challenge_id"],
        password,
        payload["public_key"],
    )
    return client.post(
        "/auth/login",
        json={
            "username": username,
            "challenge_id": payload["challenge_id"],
            "encrypted_password": encrypted_password,
        },
    )
