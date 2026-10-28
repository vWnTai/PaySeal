from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto.jws import sign_compact
from app.models.entities import (
    KeyStatus,
    Organization,
    OrganizationCertificate,
    OrganizationKey,
)
from app.services.business_verification import verification_state
from app.services.runtime import root_authority, signing_provider


def get_or_create_active_key(db: Session, organization: Organization) -> OrganizationKey:
    existing = db.scalar(
        select(OrganizationKey)
        .where(
            OrganizationKey.organization_id == organization.id,
            OrganizationKey.status == KeyStatus.ACTIVE,
        )
        .order_by(OrganizationKey.created_at.desc())
    )
    if existing:
        return existing
    kid = f"org_{organization.id.hex[:12]}_{secrets.token_hex(6)}"
    jwk = signing_provider().create_key(kid)
    key = OrganizationKey(
        organization_id=organization.id,
        kid=kid,
        provider_key_id=kid,
        public_key_jwk=jwk,
    )
    db.add(key)
    db.flush()
    issue_certificate(db, organization, key)
    return key


def issue_certificate(
    db: Session, organization: Organization, key: OrganizationKey
) -> OrganizationCertificate:
    now = datetime.now(timezone.utc)
    payload = {
        "schema": "payseal.organization-certificate.v1",
        "certificate_id": str(uuid.uuid4()),
        "organization_id": str(organization.id),
        "organization_name": organization.name,
        "tax_id": organization.tax_id,
        "domain": organization.domain,
        "public_key": key.public_key_jwk,
        "kid": key.kid,
        "assurance_level": verification_state(db, organization)["verification_level"],
        "assurance_method": verification_state(db, organization)["verification_method"],
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=365)).isoformat(),
    }
    signature = sign_compact(
        payload,
        root_authority().private_key(),
        "payseal-root-v1",
        "payseal-certificate+jws",
    )
    cert = OrganizationCertificate(
        organization_id=organization.id,
        key_id=key.id,
        payload_json=payload,
        signature_jws=signature,
        valid_from=now,
        valid_to=now + timedelta(days=365),
    )
    db.add(cert)
    db.flush()
    return cert


def rotate_key(db: Session, organization: Organization) -> OrganizationKey:
    current = get_or_create_active_key(db, organization)
    current.status = KeyStatus.RETIRED
    current.valid_until = datetime.now(timezone.utc)
    kid = f"org_{organization.id.hex[:12]}_{secrets.token_hex(6)}"
    jwk = signing_provider().rotate_key(current.provider_key_id, kid)
    key = OrganizationKey(
        organization_id=organization.id,
        kid=kid,
        provider_key_id=kid,
        public_key_jwk=jwk,
    )
    db.add(key)
    db.flush()
    issue_certificate(db, organization, key)
    return key
