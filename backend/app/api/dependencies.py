from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import Membership, Role, User
from app.security.auth import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    user = db.get(User, decode_access_token(credentials.credentials))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user"
        )
    return user


@dataclass
class TenantContext:
    organization_id: uuid.UUID
    user: User
    membership: Membership


def tenant_context(
    x_organization_id: uuid.UUID = Header(alias="X-Organization-ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == x_organization_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return TenantContext(x_organization_id, user, membership)


def require_roles(*roles: Role):
    def dependency(context: TenantContext = Depends(tenant_context)) -> TenantContext:
        if context.membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permission",
            )
        return context

    return dependency


def require_platform_reviewer(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_reviewer:
        raise HTTPException(403, "Platform reviewer permission required")
    if not user.mfa_enabled:
        raise HTTPException(403, "Platform reviewer must enable MFA")
    return user
