from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import Membership, RefreshSession, User
from app.schemas.api import (
    LoginRequest,
    MfaCode,
    MfaSetupResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security.auth import (
    create_access_token,
    hash_password,
    new_refresh_token,
    token_hash,
    verify_password,
)
from app.services.audit import add_audit_event
from app.services.runtime import encryption_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "payseal_refresh",
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
    )


def _create_session(
    db: Session, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> tuple[str, str, RefreshSession]:
    token, digest = new_refresh_token()
    csrf = secrets.token_urlsafe(32)
    session = RefreshSession(
        user_id=user_id,
        token_hash=digest,
        csrf_hash=token_hash(csrf),
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(session)
    db.flush()
    return token, csrf, session


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    db.flush()
    add_audit_event(
        db,
        organization_id=None,
        actor_id=user.id,
        event_type="REGISTER",
        object_type="user",
        object_id=str(user.id),
        data={"email": email},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        add_audit_event(
            db,
            organization_id=None,
            actor_id=user.id if user else None,
            event_type="LOGIN_FAILED",
            object_type="user",
            object_id=str(user.id) if user else "unknown",
            data={"email": data.email.lower()},
            correlation_id=request.state.correlation_id,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.mfa_enabled:
        if not data.totp_code or not user.mfa_secret_ciphertext:
            raise HTTPException(401, "MFA code required")
        secret = encryption_service().decrypt(user.mfa_secret_ciphertext, context=b"payseal-mfa-v1")
        if not pyotp.TOTP(secret).verify(data.totp_code, valid_window=1):
            raise HTTPException(401, "Invalid MFA code")
        user.mfa_verified_at = datetime.now(timezone.utc)
    refresh, csrf, _ = _create_session(db, user.id)
    add_audit_event(
        db,
        organization_id=None,
        actor_id=user.id,
        event_type="LOGIN",
        object_type="user",
        object_id=str(user.id),
        data={},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.jwt_access_ttl_minutes * 60,
        csrf_token=csrf,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    payseal_refresh: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
):
    if not payseal_refresh or not x_csrf_token:
        raise HTTPException(401, "Refresh cookie and CSRF token required")
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash(payseal_refresh))
        .with_for_update()
    )
    if session is None:
        raise HTTPException(401, "Invalid refresh token")
    if session.revoked_at is not None:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == session.family_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected")
    now = datetime.now(timezone.utc)
    expires = (
        session.expires_at
        if session.expires_at.tzinfo
        else session.expires_at.replace(tzinfo=timezone.utc)
    )
    if expires <= now or not secrets.compare_digest(session.csrf_hash, token_hash(x_csrf_token)):
        raise HTTPException(401, "Invalid refresh session")
    session.revoked_at = now
    new_token, csrf, replacement = _create_session(db, session.user_id, session.family_id)
    session.replaced_by_id = replacement.id
    db.commit()
    _set_refresh_cookie(response, new_token)
    return TokenResponse(
        access_token=create_access_token(session.user_id),
        expires_in=settings.jwt_access_ttl_minutes * 60,
        csrf_token=csrf,
    )


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    payseal_refresh: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
):
    if payseal_refresh:
        session = db.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash(payseal_refresh))
        )
        if (
            session
            and x_csrf_token
            and secrets.compare_digest(session.csrf_hash, token_hash(x_csrf_token))
        ):
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie("payseal_refresh", path="/api/v1/auth")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    result = UserResponse.model_validate(user)
    result.organizations = [
        {"id": str(item.organization_id), "role": item.role.value} for item in memberships
    ]
    return result


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = pyotp.random_base32()
    user.mfa_secret_ciphertext = encryption_service().encrypt(secret, context=b"payseal-mfa-v1")
    user.mfa_enabled = False
    db.commit()
    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="PaySeal"
        ),
    )


@router.post("/mfa/enable")
def mfa_enable(
    data: MfaCode,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.mfa_secret_ciphertext:
        raise HTTPException(409, "Run MFA setup first")
    secret = encryption_service().decrypt(user.mfa_secret_ciphertext, context=b"payseal-mfa-v1")
    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(400, "Invalid MFA code")
    user.mfa_enabled = True
    user.mfa_verified_at = datetime.now(timezone.utc)
    add_audit_event(
        db,
        organization_id=None,
        actor_id=user.id,
        event_type="MFA_ENABLED",
        object_type="user",
        object_id=str(user.id),
        data={},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {"enabled": True}


@router.post("/mfa/verify")
def mfa_verify(
    data: MfaCode, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user.mfa_enabled or not user.mfa_secret_ciphertext:
        raise HTTPException(409, "MFA is not enabled")
    secret = encryption_service().decrypt(user.mfa_secret_ciphertext, context=b"payseal-mfa-v1")
    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(401, "Invalid MFA code")
    user.mfa_verified_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "verified": True,
        "recent_window_seconds": settings.mfa_recent_window_seconds,
    }


@router.post("/mfa/disable")
def mfa_disable(
    data: MfaCode, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not user.mfa_secret_ciphertext:
        raise HTTPException(409, "MFA is not configured")
    secret = encryption_service().decrypt(user.mfa_secret_ciphertext, context=b"payseal-mfa-v1")
    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(401, "Invalid MFA code")
    user.mfa_enabled, user.mfa_secret_ciphertext, user.mfa_verified_at = (
        False,
        None,
        None,
    )
    db.commit()
    return {"enabled": False}
