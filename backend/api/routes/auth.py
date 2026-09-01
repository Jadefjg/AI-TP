from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.api.request_context import current_user_ctx
from backend.db.session import get_db
from backend.models.entities import User
from backend.schemas.dto import AuthTokenOut, ChangePasswordIn, LoginChallengeOut, LoginIn, RegisterIn, UserOut, UserProfileUpdate
from backend.services.audit_service import log_action
from backend.services.auth_service import (
    authenticate_user,
    change_user_password,
    create_access_token,
    register_user,
    revoke_access_token,
)
from backend.services.login_crypto_service import (
    LoginCryptoError,
    decrypt_change_password_payload,
    decrypt_login_password,
    issue_login_challenge,
)
from backend.services.oidc_service import (
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    new_oidc_state,
    oidc_enabled,
    provision_or_login_user,
)
from backend.services.oidc_state_store import consume_oidc_state, store_oidc_state

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


@router.get("/login-challenge", response_model=LoginChallengeOut)
def login_challenge() -> LoginChallengeOut:
    challenge = issue_login_challenge()
    return LoginChallengeOut(
        challenge_id=challenge.challenge_id,
        public_key=challenge.public_key,
        algorithm=challenge.algorithm,
        hash_alg=challenge.hash_alg,
        expires_in_sec=challenge.expires_in_sec,
    )


@router.post("/login", response_model=AuthTokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    try:
        password = decrypt_login_password(body.challenge_id, body.encrypted_password)
    except LoginCryptoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = authenticate_user(db, body.username, password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    current_user_ctx.set(user)
    access_token, expires_in_sec = create_access_token(db, user)
    log_action(
        db,
        module="auth",
        action="auth.login",
        message=f"user {user.username} logged in",
        detail={"user_id": user.id},
    )
    return AuthTokenOut(access_token=access_token, expires_in_sec=expires_in_sec, user=user)


@router.post("/register", response_model=AuthTokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    try:
        password = decrypt_login_password(body.challenge_id, body.encrypted_password)
    except LoginCryptoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        user = register_user(
            db,
            username=body.username,
            password=password,
            display_name=body.display_name,
            email=body.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    current_user_ctx.set(user)
    access_token, expires_in_sec = create_access_token(db, user)
    log_action(
        db,
        module="auth",
        action="auth.register",
        message=f"user {user.username} registered",
        detail={"user_id": user.id},
    )
    return AuthTokenOut(access_token=access_token, expires_in_sec=expires_in_sec, user=user)


@router.post("/logout", response_model=dict)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if credentials:
        revoke_access_token(db, credentials.credentials)
    log_action(
        db,
        module="auth",
        action="auth.logout",
        message=f"user {user.username} logged out",
        detail={"user_id": user.id},
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        user.display_name = (data["display_name"] or "").strip() or None
    if "email" in data:
        user.email = data["email"]
    db.commit()
    db.refresh(user)
    log_action(
        db,
        module="auth",
        action="auth.profile_updated",
        message=f"user {user.username} updated profile",
        detail={"user_id": user.id},
    )
    return user


@router.post("/change-password", response_model=AuthTokenOut)
def change_password(
    body: ChangePasswordIn,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    try:
        current_password, new_password = decrypt_change_password_payload(
            body.challenge_id,
            body.encrypted_payload,
        )
        change_user_password(db, user, current_password, new_password)
    except LoginCryptoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if credentials:
        revoke_access_token(db, credentials.credentials)
    access_token, expires_in_sec = create_access_token(db, user)
    log_action(
        db,
        module="auth",
        action="auth.password_changed",
        message=f"user {user.username} changed password",
        detail={"user_id": user.id},
    )
    return AuthTokenOut(access_token=access_token, expires_in_sec=expires_in_sec, user=user)


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured")
    state = new_oidc_state()
    store_oidc_state(state)
    return RedirectResponse(build_authorization_url(state))


@router.get("/oidc/callback", response_model=AuthTokenOut)
def oidc_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not configured")
    if not consume_oidc_state(state):
        raise HTTPException(status_code=400, detail="invalid or expired OIDC state")
    tokens = exchange_code_for_tokens(code)
    access = tokens.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="OIDC access_token missing")
    claims = fetch_userinfo(access)
    user = provision_or_login_user(db, claims)
    current_user_ctx.set(user)
    platform_token, expires_in_sec = create_access_token(db, user)
    log_action(
        db,
        module="auth",
        action="auth.oidc_login",
        message=f"user {user.username} logged in via OIDC",
        detail={"user_id": user.id},
    )
    return AuthTokenOut(access_token=platform_token, expires_in_sec=expires_in_sec, user=user)
