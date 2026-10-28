from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import Beneficiary, Membership, Organization, Role, User
from app.security.auth import hash_password
from app.services.keys import get_or_create_active_key
from app.services.runtime import encryption_service

DEMO_PASSWORD = "PaySeal-Demo-2026!"


def run() -> None:
    if settings.environment == "production":
        raise RuntimeError("Demo accounts must not be installed in production")
    db = SessionLocal()
    try:
        users: dict[str, User] = {}
        for email, name in [
            ("maker@demo.local", "Demo Maker"),
            ("approver@demo.local", "Demo Approver"),
            ("owner@demo.local", "Demo Owner"),
        ]:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(
                    email=email,
                    full_name=name,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
                db.add(user)
                db.flush()
            users[email] = user
        organization = db.scalar(select(Organization).where(Organization.tax_id == "0101234567"))
        if not organization:
            organization = Organization(
                name="CÔNG TY PAYSEAL DEMO",
                tax_id="0101234567",
                domain="demo.payseal.local",
                verification_level=2,
            )
            db.add(organization)
            db.flush()
        for email, role in [
            ("maker@demo.local", Role.MAKER),
            ("approver@demo.local", Role.APPROVER),
            ("owner@demo.local", Role.OWNER),
        ]:
            if not db.scalar(
                select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.user_id == users[email].id,
                )
            ):
                db.add(
                    Membership(
                        organization_id=organization.id,
                        user_id=users[email].id,
                        role=role,
                    )
                )
        if not db.scalar(
            select(Beneficiary).where(
                Beneficiary.organization_id == organization.id,
                Beneficiary.name == "CÔNG TY ABC",
            )
        ):
            crypto = encryption_service()
            db.add(
                Beneficiary(
                    organization_id=organization.id,
                    name="CÔNG TY ABC",
                    bank_code="VCB",
                    account_ciphertext=crypto.encrypt("123456789"),
                    account_lookup_hash=crypto.lookup_hash("123456789"),
                    account_last4="6789",
                    verified_at=datetime.now(timezone.utc),
                )
            )
        get_or_create_active_key(db, organization)
        db.commit()
        print(f"Seed complete. Organization ID: {organization.id}")
        print(f"Demo users use password: {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
