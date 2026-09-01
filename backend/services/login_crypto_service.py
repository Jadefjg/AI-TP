from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_CHALLENGES: dict[str, float] = {}
_PRIVATE_KEY: RSAPrivateKey | None = None
_REDIS_CLIENT: Any | None = None
_REDIS_CHECKED = False

_CHALLENGE_KEY_PREFIX = "ai-tp:login:challenge:"
_PRIVATE_KEY_REDIS_KEY = "ai-tp:login-crypto:private-key"


class LoginCryptoError(ValueError):
    pass


@dataclass(frozen=True)
class LoginChallenge:
    challenge_id: str
    public_key: str
    algorithm: str
    hash_alg: str
    expires_in_sec: int


def _redis_client() -> Any | None:
    global _REDIS_CLIENT, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _REDIS_CLIENT
    _REDIS_CHECKED = True
    url = (get_settings().redis_url or "").strip()
    if not url:
        return None
    try:
        import redis  # type: ignore[import-untyped]

        client = redis.from_url(url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        logger.info("Login crypto: using Redis for challenges and shared RSA key")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login crypto: Redis unavailable (%s), using in-memory", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _ttl_sec() -> int:
    return max(get_settings().auth_login_challenge_ttl_sec, 60)


def _purge_expired_challenges() -> None:
    ttl = _ttl_sec()
    now = time.time()
    expired = [key for key, created_at in _CHALLENGES.items() if now - created_at > ttl]
    for key in expired:
        _CHALLENGES.pop(key, None)


def _serialize_private_key(key: RSAPrivateKey) -> str:
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


def _deserialize_private_key(pem: str) -> RSAPrivateKey:
    loaded = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(loaded, RSAPrivateKey):
        raise LoginCryptoError("invalid RSA private key")
    return loaded


def _private_key() -> RSAPrivateKey:
    global _PRIVATE_KEY
    if _PRIVATE_KEY is not None:
        return _PRIVATE_KEY

    client = _redis_client()
    if client:
        pem = client.get(_PRIVATE_KEY_REDIS_KEY)
        if pem:
            _PRIVATE_KEY = _deserialize_private_key(pem)
            return _PRIVATE_KEY
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = _serialize_private_key(key)
        if client.set(_PRIVATE_KEY_REDIS_KEY, pem, nx=True):
            logger.info("generated shared RSA key pair for login encryption (Redis)")
            _PRIVATE_KEY = key
            return _PRIVATE_KEY
        stored = client.get(_PRIVATE_KEY_REDIS_KEY)
        if not stored:
            raise LoginCryptoError("failed to initialize login encryption key")
        _PRIVATE_KEY = _deserialize_private_key(stored)
        return _PRIVATE_KEY

    if _PRIVATE_KEY is None:
        _PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        logger.info("generated ephemeral RSA key pair for login encryption")
    return _PRIVATE_KEY


def _public_key_spki_b64() -> str:
    public_bytes = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(public_bytes).decode("ascii")


def _store_challenge(challenge_id: str) -> None:
    client = _redis_client()
    if client:
        client.setex(f"{_CHALLENGE_KEY_PREFIX}{challenge_id}", _ttl_sec(), "1")
        return
    _purge_expired_challenges()
    _CHALLENGES[challenge_id] = time.time()


def _consume_challenge(challenge_id: str) -> bool:
    if not challenge_id:
        return False
    client = _redis_client()
    if client:
        deleted = client.delete(f"{_CHALLENGE_KEY_PREFIX}{challenge_id}")
        return int(deleted) > 0
    _purge_expired_challenges()
    created_at = _CHALLENGES.pop(challenge_id, None)
    if created_at is None:
        return False
    if time.time() - created_at > _ttl_sec():
        return False
    return True


def issue_login_challenge() -> LoginChallenge:
    challenge_id = secrets.token_urlsafe(24)
    _store_challenge(challenge_id)
    return LoginChallenge(
        challenge_id=challenge_id,
        public_key=_public_key_spki_b64(),
        algorithm="RSA-OAEP",
        hash_alg="SHA-256",
        expires_in_sec=_ttl_sec(),
    )


def consume_login_challenge(challenge_id: str) -> bool:
    return _consume_challenge(challenge_id)


def decrypt_challenge_payload(challenge_id: str, encrypted_b64: str) -> dict:
    if not consume_login_challenge(challenge_id):
        raise LoginCryptoError("invalid or expired login challenge")

    try:
        ciphertext = base64.b64decode(encrypted_b64, validate=True)
        plaintext = _private_key().decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        payload = json.loads(plaintext.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LoginCryptoError("invalid encrypted payload") from exc

    if not isinstance(payload, dict):
        raise LoginCryptoError("invalid encrypted payload")
    if payload.get("challenge_id") != challenge_id:
        raise LoginCryptoError("login challenge mismatch")
    return payload


def decrypt_login_password(challenge_id: str, encrypted_password_b64: str) -> str:
    payload = decrypt_challenge_payload(challenge_id, encrypted_password_b64)
    password = payload.get("password")
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        raise LoginCryptoError("invalid password payload")
    return password


def decrypt_change_password_payload(challenge_id: str, encrypted_payload_b64: str) -> tuple[str, str]:
    payload = decrypt_challenge_payload(challenge_id, encrypted_payload_b64)
    current_password = payload.get("current_password")
    new_password = payload.get("new_password")
    if not isinstance(current_password, str) or not (8 <= len(current_password) <= 128):
        raise LoginCryptoError("invalid current password payload")
    if not isinstance(new_password, str) or not (8 <= len(new_password) <= 128):
        raise LoginCryptoError("invalid new password payload")
    return current_password, new_password


def encrypt_login_password_for_tests(challenge_id: str, password: str, public_key_b64: str) -> str:
    """Test helper mirroring browser Web Crypto RSA-OAEP encryption."""
    return encrypt_challenge_payload_for_tests(
        challenge_id,
        {"password": password},
        public_key_b64,
    )


def encrypt_challenge_payload_for_tests(
    challenge_id: str,
    payload: dict,
    public_key_b64: str,
) -> str:
    public_key = serialization.load_der_public_key(base64.b64decode(public_key_b64))
    body = json.dumps({"challenge_id": challenge_id, **payload}, separators=(",", ":")).encode("utf-8")
    ciphertext = public_key.encrypt(
        body,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def encrypt_change_password_for_tests(
    challenge_id: str,
    current_password: str,
    new_password: str,
    public_key_b64: str,
) -> str:
    return encrypt_challenge_payload_for_tests(
        challenge_id,
        {"current_password": current_password, "new_password": new_password},
        public_key_b64,
    )


def reset_login_crypto_state_for_tests() -> None:
    global _PRIVATE_KEY, _REDIS_CHECKED, _REDIS_CLIENT
    _CHALLENGES.clear()
    _PRIVATE_KEY = None
    _REDIS_CHECKED = False
    _REDIS_CLIENT = None
