from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import get_db
from backend.services.auth_service import get_user_by_access_token, user_has_permission

_bearer = HTTPBearer(auto_error=False)


async def verify_metrics_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Protect /metrics when METRICS_AUTH_ENABLED=true.

    - Prefer METRICS_BEARER_TOKEN (Prometheus scrape via Authorization or X-Metrics-Token).
    - Else require JWT Bearer with system.read.
    """
    settings = get_settings()
    if not settings.metrics_auth_enabled:
        return

    configured = (settings.metrics_bearer_token or "").strip()
    if configured:
        presented = ""
        if credentials and credentials.scheme.lower() == "bearer":
            presented = credentials.credentials.strip()
        if not presented:
            presented = (request.headers.get("X-Metrics-Token") or "").strip()
        if presented and hmac.compare_digest(presented, configured):
            return
        raise HTTPException(status_code=401, detail="invalid metrics credentials")

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="authentication required for metrics")
    user = get_user_by_access_token(db, credentials.credentials)
    if not user or not user_has_permission(user, "system.read"):
        raise HTTPException(status_code=403, detail="permission denied: system.read required for metrics")
