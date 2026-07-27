from __future__ import annotations

import secrets
import urllib.parse
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.models.entities import Role, User
from backend.services.auth_service import create_access_token, hash_password
from backend.services.member_service import attach_oidc_user_to_organization


def oidc_enabled() -> bool:
    s = get_settings()
    return bool(s.oidc_enabled and s.oidc_issuer_url.strip() and s.oidc_client_id.strip())


def _issuer_base() -> str:
    return get_settings().oidc_issuer_url.rstrip("/")


def discovery_document() -> dict[str, Any]:
    url = f"{_issuer_base()}/.well-known/openid-configuration"
    with httpx.Client(timeout=15.0) as client:
        res = client.get(url)
    if not res.is_success:
        raise HTTPException(status_code=502, detail="OIDC discovery failed")
    return res.json()


def build_authorization_url(state: str) -> str:
    settings = get_settings()
    doc = discovery_document()
    auth_endpoint = doc.get("authorization_endpoint")
    if not auth_endpoint:
        raise HTTPException(status_code=502, detail="OIDC authorization_endpoint missing")
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "scope": settings.oidc_scopes,
        "redirect_uri": settings.oidc_redirect_uri,
        "state": state,
    }
    return f"{auth_endpoint}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    settings = get_settings()
    doc = discovery_document()
    token_endpoint = doc.get("token_endpoint")
    if not token_endpoint:
        raise HTTPException(status_code=502, detail="OIDC token_endpoint missing")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    with httpx.Client(timeout=15.0) as client:
        res = client.post(token_endpoint, data=data)
    if not res.is_success:
        raise HTTPException(status_code=401, detail="OIDC token exchange failed")
    return res.json()


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    doc = discovery_document()
    userinfo_endpoint = doc.get("userinfo_endpoint")
    if not userinfo_endpoint:
        raise HTTPException(status_code=502, detail="OIDC userinfo_endpoint missing")
    with httpx.Client(timeout=15.0) as client:
        res = client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"})
    if not res.is_success:
        raise HTTPException(status_code=401, detail="OIDC userinfo failed")
    return res.json()


def _organization_slug_from_claims(claims: dict[str, Any]) -> str | None:
    settings = get_settings()
    key = (settings.oidc_organization_claim or "org_slug").strip()
    for candidate in (key, "org_slug", "tenant", "organization", "org"):
        val = claims.get(candidate)
        if val:
            return str(val).strip().lower()
    return None


def provision_or_login_user(db: Session, claims: dict[str, Any]) -> User:
    username = (
        str(claims.get("preferred_username") or claims.get("email") or claims.get("sub") or "")
    ).strip()
    if not username:
        raise HTTPException(status_code=401, detail="OIDC claims missing subject")
    user = (
        db.query(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .filter(User.username == username)
        .one_or_none()
    )
    created = False
    if not user:
        created = True
        user = User(
            username=username[:64],
            display_name=str(claims.get("name") or username)[:255],
            email=str(claims.get("email") or "")[:320] or None,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            is_active=True,
            organization_id=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="user is inactive")
    if created or user.organization_id is None:
        attach_oidc_user_to_organization(db, user=user, org_slug=_organization_slug_from_claims(claims))
        user = (
            db.query(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .filter(User.id == user.id)
            .one()
        )
    return user


def new_oidc_state() -> str:
    return secrets.token_urlsafe(24)
