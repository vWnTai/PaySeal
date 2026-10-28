from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import BusinessVerification, KeyStatus, Organization, OrganizationKey


def profile_of(organization: Organization) -> dict[str, str]:
    return {"name": organization.name, "tax_id": organization.tax_id, "domain": organization.domain}


def latest_verification(db: Session, organization: Organization) -> BusinessVerification | None:
    return db.scalar(
        select(BusinessVerification)
        .where(BusinessVerification.organization_id == organization.id)
        .order_by(BusinessVerification.created_at.desc(), BusinessVerification.id.desc())
        .limit(1)
    )


def verification_state(db: Session, organization: Organization) -> dict:
    latest = latest_verification(db, organization)
    status = (
        latest.status
        if latest
        else ("DEMO_SEEDED" if organization.verification_level >= 2 else "UNVERIFIED")
    )
    if latest and latest.status == "APPROVED":
        expiry = latest.valid_until
        if not expiry or (
            expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
        ) <= datetime.now(timezone.utc):
            status = "EXPIRED"
        elif latest.profile != profile_of(organization):
            status = "STALE"
    return {
        "verification_status": status,
        "verification_level": 2 if status in {"APPROVED", "DEMO_SEEDED"} else 0,
        "verification_method": "MANUAL_REVIEW"
        if status == "APPROVED"
        else ("DEMO_SEED" if status == "DEMO_SEEDED" else None),
        "verification_valid_until": latest.valid_until if latest else None,
    }


def require_verified_business(db: Session, organization: Organization) -> None:
    if verification_state(db, organization)["verification_status"] != "APPROVED":
        raise HTTPException(409, "Business verification required for transfers")
    if organization.status.value != "ACTIVE":
        raise HTTPException(409, "Organization is suspended")


def retire_active_certificates(db: Session, organization: Organization) -> None:
    # New signatures receive a certificate with the new assurance. Old signed documents stay immutable.
    for key in db.scalars(
        select(OrganizationKey).where(
            OrganizationKey.organization_id == organization.id,
            OrganizationKey.status == KeyStatus.ACTIVE,
        )
    ):
        key.status = KeyStatus.RETIRED
        key.valid_until = datetime.now(timezone.utc)


def approve_verification(
    db: Session, organization: Organization, submission: BusinessVerification
) -> None:
    organization.verification_level = 2
    submission.valid_until = datetime.now(timezone.utc) + timedelta(days=365)
    retire_active_certificates(db, organization)
