from __future__ import annotations

from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.services.login_crypto_service import (
    LoginCryptoError,
    decrypt_login_password,
    encrypt_login_password_for_tests,
    issue_login_challenge,
    reset_login_crypto_state_for_tests,
)
from tests.auth_helpers import login_with_encrypted_password


def test_login_challenge_and_encrypted_login(client: TestClient):
    challenge = client.get("/auth/login-challenge")
    assert challenge.status_code == 200
    body = challenge.json()
    assert body["algorithm"] == "RSA-OAEP"
    assert body["hash_alg"] == "SHA-256"
    assert body["challenge_id"]

    settings = get_settings()
    encrypted = encrypt_login_password_for_tests(
        body["challenge_id"],
        settings.bootstrap_admin_password,
        body["public_key"],
    )
    password = decrypt_login_password(body["challenge_id"], encrypted)
    assert password == settings.bootstrap_admin_password

    res = login_with_encrypted_password(
        client,
        username=settings.bootstrap_admin_username,
        password=settings.bootstrap_admin_password,
    )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_login_challenge_is_single_use(client: TestClient):
    reset_login_crypto_state_for_tests()
    challenge = issue_login_challenge()
    encrypted = encrypt_login_password_for_tests(
        challenge.challenge_id,
        "admin123",
        challenge.public_key,
    )
    decrypt_login_password(challenge.challenge_id, encrypted)
    try:
        decrypt_login_password(challenge.challenge_id, encrypted)
        assert False, "expected challenge reuse to fail"
    except LoginCryptoError:
        pass
