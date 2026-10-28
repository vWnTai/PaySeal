from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.models.entities import (
    KeyStatus,
    OrganizationKey,
    PaymentRequest,
    PaymentRequestVersion,
)
from sqlalchemy import select

from tests.conftest import FakeStorage

PASSWORD = "Strong-Demo-Password-2026!"


def register(client, email: str, name: str):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text


def login(client, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id:
        headers["X-Organization-ID"] = organization_id
    return headers


def test_end_to_end_integrity_revocation_maker_checker_and_idor(client, db_session):
    register(client, "maker@test.local", "Maker")
    register(client, "approver@test.local", "Approver")
    register(client, "outsider@test.local", "Outsider")
    maker_token = login(client, "maker@test.local")
    organization = client.post(
        "/api/v1/organizations",
        headers=auth(maker_token),
        json={"name": "ACME", "tax_id": "TAX-001", "domain": "acme.test"},
    ).json()
    org_id = organization["id"]
    member = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(maker_token),
        json={"email": "approver@test.local", "role": "APPROVER"},
    )
    assert member.status_code == 201
    beneficiary = client.post(
        "/api/v1/beneficiaries",
        headers=auth(maker_token, org_id),
        json={"name": "Supplier", "bank_code": "VCB", "account_number": "123456789"},
    )
    assert beneficiary.status_code == 201
    beneficiary_id = beneficiary.json()["id"]
    body = {
        "invoice_reference": "INV-1",
        "currency": "VND",
        "amount_minor": 5_000_000,
        "beneficiary_id": beneficiary_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    first = client.post(
        "/api/v1/payment-requests",
        headers={**auth(maker_token, org_id), "Idempotency-Key": "create-1"},
        json=body,
    )
    duplicate = client.post(
        "/api/v1/payment-requests",
        headers={**auth(maker_token, org_id), "Idempotency-Key": "create-1"},
        json=body,
    )
    assert first.status_code == duplicate.status_code == 201
    assert first.json()["id"] == duplicate.json()["id"]
    payment_id = first.json()["id"]
    assert (
        client.post(
            f"/api/v1/payment-requests/{payment_id}/submit",
            headers=auth(maker_token, org_id),
        ).status_code
        == 200
    )
    self_approval = client.post(
        f"/api/v1/payment-requests/{payment_id}/approve",
        headers=auth(maker_token, org_id),
        json={},
    )
    assert self_approval.status_code == 403
    outsider_token = login(client, "outsider@test.local")
    assert (
        client.get(
            f"/api/v1/payment-requests/{payment_id}",
            headers=auth(outsider_token, org_id),
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/beneficiaries/{beneficiary_id}",
            headers=auth(outsider_token, org_id),
            json={"name": "Stolen"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/payment-requests/{payment_id}/approve",
            headers=auth(outsider_token, org_id),
            json={},
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/audit-events", headers=auth(outsider_token, org_id)).status_code == 404
    )
    approver_token = login(client, "approver@test.local")
    approved = client.post(
        f"/api/v1/payment-requests/{payment_id}/approve",
        headers=auth(approver_token, org_id),
        json={},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    signed = client.post(
        f"/api/v1/payment-requests/{payment_id}/sign",
        headers={**auth(approver_token, org_id), "Idempotency-Key": "sign-1"},
        json={},
    )
    assert signed.status_code == 200, signed.text
    public_url = signed.json()["public_url"]
    token = urlparse(public_url).path.rsplit("/", 1)[-1]
    verified = client.get(f"/api/v1/public/verify/{token}")
    assert verified.status_code == 200 and verified.json()["status"] == "VERIFIED"
    payment = db_session.get(PaymentRequest, uuid.UUID(payment_id))
    original = FakeStorage.objects[payment.document_object_key]
    match = client.post(
        f"/api/v1/public/verify/{token}/document",
        files={"document": ("original.pdf", original, "application/pdf")},
    )
    assert match.json()["document_integrity"] == "MATCH"
    mismatch = client.post(
        f"/api/v1/public/verify/{token}/document",
        files={"document": ("modified.pdf", original + b"changed", "application/pdf")},
    )
    assert mismatch.json()["status"] == "DOCUMENT_MISMATCH"
    version = db_session.scalar(
        select(PaymentRequestVersion).where(PaymentRequestVersion.payment_request_id == payment.id)
    )
    original_expiry = version.expires_at
    version.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/api/v1/public/verify/{token}").json()["status"] == "EXPIRED"
    version.expires_at = original_expiry
    key = db_session.scalar(
        select(OrganizationKey).where(OrganizationKey.kid == payment.signature_kid)
    )
    key.status = KeyStatus.COMPROMISED
    key.compromised_at = payment.signed_at + timedelta(seconds=1)
    db_session.commit()
    before_compromise = client.get(f"/api/v1/public/verify/{token}").json()
    assert before_compromise["status"] == "VERIFIED" and before_compromise["warnings"]
    key.compromised_at = payment.signed_at - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/api/v1/public/verify/{token}").json()["status"] == "KEY_COMPROMISED"
    key.status, key.compromised_at = KeyStatus.RETIRED, None
    db_session.commit()
    revoked = client.post(
        f"/api/v1/payment-requests/{payment_id}/revoke",
        headers=auth(approver_token, org_id),
        json={"reason": "Invoice cancelled"},
    )
    assert revoked.status_code == 200
    assert client.get(f"/api/v1/public/verify/{token}").json()["status"] == "REVOKED"
