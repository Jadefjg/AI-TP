from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.api.request_context import current_user_ctx
from backend.db.session import get_db
from backend.models.entities import User
from backend.services.auth_service import get_user_by_access_token, user_has_permission

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="authentication required")
    user = get_user_by_access_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    current_user_ctx.set(user)
    return user


def require_permission(code: str):
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if not user_has_permission(user, code):
            raise HTTPException(status_code=403, detail=f"permission denied: {code}")
        return user

    return _dependency


def require_any_permission(*codes: str):
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if not any(user_has_permission(user, code) for code in codes):
            joined = ", ".join(codes)
            raise HTTPException(status_code=403, detail=f"permission denied: one of {joined}")
        return user

    return _dependency
