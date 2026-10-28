from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.entities import (
    KeyStatus,
    Membership,
    Organization,
    OrganizationKey,
    Role,
    User,
)
from app.schemas.api import (
    MemberCreate,
    MemberPatch,
    OrganizationCreate,
    OrganizationPatch,
    OrganizationResponse,
)
from app.services.audit import add_audit_event
from app.services.business_verification import (
    latest_verification,
    retire_active_certificates,
    verification_state,
)
from app.services.keys import rotate_key
from app.services.runtime import signing_provider

router = APIRouter(prefix="/organizations", tags=["Organizations"])


def _membership(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: set[Role] | None = None,
) -> Membership:
    member = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user_id
        )
    )
    if member is None:
        raise HTTPException(404, "Organization not found")
    if roles and member.role not in roles:
        raise HTTPException(403, "Insufficient organization permission")
    return member


@router.post("", response_model=OrganizationResponse, status_code=201)
def create_organization(
    data: OrganizationCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    organization = Organization(
        name=data.name,
        tax_id=data.tax_id,
        domain=data.domain.lower(),
        verification_level=0,
    )
    db.add(organization)
    db.flush()
    db.add(Membership(organization_id=organization.id, user_id=user.id, role=Role.OWNER))
    add_audit_event(
        db,
        organization_id=organization.id,
        actor_id=user.id,
        event_type="CREATE_ORGANIZATION",
        object_type="organization",
        object_id=str(organization.id),
        data={"name": organization.name},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return OrganizationResponse.model_validate(organization).model_copy(
        update=verification_state(db, organization)
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    return OrganizationResponse.model_validate(organization).model_copy(
        update=verification_state(db, organization)
    )


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def patch_organization(
    organization_id: uuid.UUID,
    data: OrganizationPatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    organization = db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    assert organization is not None
    values = data.model_dump(exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(422, "Organization identity cannot be empty")
    previous = latest_verification(db, organization)
    if previous and previous.status == "PENDING" and values:
        raise HTTPException(409, "Organization identity is locked during verification")
    changed = any(
        getattr(organization, key) != (value.lower() if key == "domain" else value)
        for key, value in values.items()
    )
    for key, value in values.items():
        setattr(organization, key, value.lower() if key == "domain" else value)
    if changed:
        organization.verification_level = 0
        if previous and previous.status == "APPROVED":
            previous.status = "STALE"
        retire_active_certificates(db, organization)
        add_audit_event(
            db,
            organization_id=organization_id,
            actor_id=user.id,
            event_type="UPDATE_ORGANIZATION_IDENTITY",
            object_type="organization",
            object_id=str(organization_id),
            data={"fields": list(values), "verification_reset": True},
            correlation_id=request.state.correlation_id,
        )
    db.commit()
    return OrganizationResponse.model_validate(organization).model_copy(
        update=verification_state(db, organization)
    )


@router.get("/{organization_id}/members")
def list_members(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER, Role.AUDITOR})
    members = db.scalars(
        select(Membership).where(Membership.organization_id == organization_id)
    ).all()
    return [
        {
            "id": item.id,
            "user_id": item.user_id,
            "email": item.user.email,
            "full_name": item.user.full_name,
            "role": item.role.value,
            "created_at": item.created_at,
        }
        for item in members
    ]


@router.post("/{organization_id}/members", status_code=201)
def add_member(
    organization_id: uuid.UUID,
    data: MemberCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    try:
        role = Role(data.role)
    except ValueError as exc:
        raise HTTPException(422, "Invalid role") from exc
    target = db.scalar(select(User).where(User.email == data.email.lower()))
    if target is None:
        raise HTTPException(404, "User must register before being added")
    if db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == target.id,
        )
    ):
        raise HTTPException(409, "User is already a member")
    member = Membership(organization_id=organization_id, user_id=target.id, role=role)
    db.add(member)
    db.flush()
    add_audit_event(
        db,
        organization_id=organization_id,
        actor_id=user.id,
        event_type="ADD_MEMBER",
        object_type="membership",
        object_id=str(member.id),
        data={"user_id": str(target.id), "role": role.value},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {"id": member.id, "user_id": member.user_id, "role": member.role.value}


@router.patch("/{organization_id}/members/{member_id}")
def patch_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    data: MemberPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    member = db.scalar(
        select(Membership).where(
            Membership.id == member_id, Membership.organization_id == organization_id
        )
    )
    if member is None:
        raise HTTPException(404, "Member not found")
    try:
        member.role = Role(data.role)
    except ValueError as exc:
        raise HTTPException(422, "Invalid role") from exc
    db.commit()
    return {"id": member.id, "user_id": member.user_id, "role": member.role.value}


@router.post("/{organization_id}/keys/rotate")
def rotate_organization_key(
    organization_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    organization = db.get(Organization, organization_id)
    assert organization is not None
    key = rotate_key(db, organization)
    add_audit_event(
        db,
        organization_id=organization_id,
        actor_id=user.id,
        event_type="ROTATE_KEY",
        object_type="organization_key",
        object_id=str(key.id),
        data={"kid": key.kid},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {
        "kid": key.kid,
        "status": key.status.value,
        "public_key_jwk": key.public_key_jwk,
    }


@router.post("/{organization_id}/keys/{kid}/compromise")
def compromise_key(
    organization_id: uuid.UUID,
    kid: str,
    reason: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    key = db.scalar(
        select(OrganizationKey).where(
            OrganizationKey.organization_id == organization_id,
            OrganizationKey.kid == kid,
        )
    )
    if key is None:
        raise HTTPException(404, "Key not found")
    key.status, key.compromised_at, key.revocation_reason = (
        KeyStatus.COMPROMISED,
        datetime.now(timezone.utc),
        reason[:500],
    )
    add_audit_event(
        db,
        organization_id=organization_id,
        actor_id=user.id,
        event_type="REVOKE_KEY",
        object_type="organization_key",
        object_id=str(key.id),
        data={"kid": key.kid, "status": "COMPROMISED", "reason": reason[:500]},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {
        "kid": key.kid,
        "status": key.status.value,
        "compromised_at": key.compromised_at,
    }


@router.post("/{organization_id}/keys/{kid}/revoke")
def revoke_key(
    organization_id: uuid.UUID,
    kid: str,
    reason: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    key = db.scalar(
        select(OrganizationKey)
        .where(
            OrganizationKey.organization_id == organization_id,
            OrganizationKey.kid == kid,
        )
        .with_for_update()
    )
    if key is None:
        raise HTTPException(404, "Key not found")
    if key.status == KeyStatus.REVOKED:
        return {
            "kid": key.kid,
            "status": key.status.value,
            "revoked_at": key.revoked_at,
        }
    signing_provider().revoke_key(key.provider_key_id)
    key.status, key.revoked_at, key.revocation_reason = (
        KeyStatus.REVOKED,
        datetime.now(timezone.utc),
        reason[:500],
    )
    add_audit_event(
        db,
        organization_id=organization_id,
        actor_id=user.id,
        event_type="REVOKE_KEY",
        object_type="organization_key",
        object_id=str(key.id),
        data={"kid": key.kid, "status": "REVOKED", "reason": reason[:500]},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return {"kid": key.kid, "status": key.status.value, "revoked_at": key.revoked_at}
