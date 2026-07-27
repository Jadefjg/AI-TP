from __future__ import annotations

import base64
import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import Project, ProjectAiCredential
from backend.services.tenant_service import get_project_for_user

logger = logging.getLogger(__name__)


def _fernet():
    from cryptography.fernet import Fernet

    settings = get_settings()
    raw = (settings.ai_credentials_encryption_key or "").strip()
    if not raw:
        digest = hashlib.sha256(b"ai-tp-dev-credentials").digest()
        raw = base64.urlsafe_b64encode(digest).decode("ascii")
    else:
        try:
            Fernet(raw.encode("ascii"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail="AI_CREDENTIALS_ENCRYPTION_KEY must be a valid Fernet key",
            ) from exc
    return Fernet(raw.encode("ascii"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def get_project_llm_override(db: Session, project: Project) -> dict[str, str] | None:
    row = (
        db.query(ProjectAiCredential)
        .filter(ProjectAiCredential.project_id == project.id, ProjectAiCredential.enabled.is_(True))
        .one_or_none()
    )
    if not row or not row.api_key_encrypted:
        return None
    try:
        api_key = decrypt_secret(row.api_key_encrypted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to decrypt project credential project_id=%s: %s", project.id, exc)
        return None
    settings = get_settings()
    return {
        "provider": row.provider,
        "api_base_url": (row.api_base_url or settings.openai_base_url).rstrip("/"),
        "api_key": api_key,
        "model": (row.model_override or settings.openai_model).strip(),
    }


def upsert_project_credential(
    db: Session,
    *,
    project: Project,
    provider: str,
    api_base_url: str | None,
    api_key: str | None,
    model_override: str | None,
    enabled: bool,
) -> ProjectAiCredential:
    row = db.query(ProjectAiCredential).filter(ProjectAiCredential.project_id == project.id).one_or_none()
    if not row:
        row = ProjectAiCredential(project_id=project.id, provider=provider)
        db.add(row)
    row.provider = provider
    row.api_base_url = api_base_url
    row.model_override = model_override
    row.enabled = enabled
    if api_key:
        row.api_key_encrypted = encrypt_secret(api_key.strip())
    db.commit()
    db.refresh(row)
    return row


def credential_status(db: Session, project: Project) -> dict:
    row = db.query(ProjectAiCredential).filter(ProjectAiCredential.project_id == project.id).one_or_none()
    if not row:
        return {"configured": False, "enabled": False, "provider": None, "api_key_masked": None}
    masked = None
    if row.api_key_encrypted:
        try:
            masked = mask_secret(decrypt_secret(row.api_key_encrypted))
        except Exception:  # noqa: BLE001
            masked = "****"
    return {
        "configured": bool(row.api_key_encrypted),
        "enabled": row.enabled,
        "provider": row.provider,
        "api_base_url": row.api_base_url,
        "model_override": row.model_override,
        "api_key_masked": masked,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def require_project_credential_access(db: Session, user, project_id: int) -> Project:
    return get_project_for_user(db, user, project_id)
