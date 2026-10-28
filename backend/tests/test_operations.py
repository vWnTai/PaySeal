import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from app.core.config import settings
from app.models.entities import (
    BusinessVerification,
    Membership,
    Organization,
    PaymentRequestVersion,
    Role,
    SandboxReceipt,
    Transfer,
    TransferEvent,
    User,
)
from app.security.auth import create_access_token, hash_password
from app.services.runtime import encryption_service
from sqlalchemy import func, select

from tests.conftest import FakeStorage


@pytest.fixture()
def actors(db_session):
    password_hash = hash_password("Strong-Demo-Password-2026!")
    people = {}
    for name in ("maker", "approver", "reviewer", "outsider"):
        secret = pyotp.random_base32()
        user = User(
            email=f"{name}@operations.test",
            full_name=name,
            password_hash=password_hash,
            mfa_enabled=name != "outsider",
            mfa_secret_ciphertext=encryption_service().encrypt(secret, context=b"payseal-mfa-v1"),
            mfa_verified_at=datetime.now(timezone.utc),
            is_platform_reviewer=name == "reviewer",
        )
        db_session.add(user)
        db_session.flush()
        people[name] = {
            "user": user,
            "secret": secret,
            "Authorization": "Bearer " + create_access_token(user.id),
        }
    org = Organization(
        name="Operations Ltd", tax_id="OPS-001", domain="operations.test", verification_level=0
    )
    other = Organization(name="Other Ltd", tax_id="OPS-002", domain="other.test")
    db_session.add_all([org, other])
    db_session.flush()
    for name, role in (("maker", Role.OWNER), ("approver", Role.APPROVER)):
        db_session.add(
            Membership(organization_id=org.id, user_id=people[name]["user"].id, role=role)
        )
    db_session.add(
        Membership(organization_id=other.id, user_id=people["outsider"]["user"].id, role=Role.OWNER)
    )
    db_session.commit()
    for actor in people.values():
        actor["headers"] = {
            "Authorization": actor["Authorization"],
            "X-Organization-ID": str(org.id),
        }
    return people, org


def submit(client, actors, content=b"%PDF-1.7 test business evidence", expected=201):
    people, org = actors
    response = client.post(
        f"/api/v1/organizations/{org.id}/verification",
        headers=people["maker"]["headers"],
        data={
            "registration_number": "REG-001",
            "representative_name": "Legal Representative",
            "registered_address": "123 Test Street",
            "contact_email": "business@operations.test",
            "attested": "true",
        },
        files={"document": ("evidence.pdf", content, "application/pdf")},
    )
    assert response.status_code == expected, response.text
    return response


def approve(client, actors, submission_id):
    people, _ = actors
    response = client.post(
        f"/api/v1/platform/verifications/{submission_id}/review",
        headers=people["reviewer"]["headers"],
        json={
            "decision": "APPROVED",
            "reason": "Independent registration, tax and authority evidence checked.",
            "registration_checked": True,
            "tax_checked": True,
            "authority_checked": True,
            "totp_code": pyotp.TOTP(people["reviewer"]["secret"]).now(),
        },
    )
    assert response.status_code == 200, response.text
    return response


def signed_payment(client, actors, *, verified=True, bank_code="VCB"):
    people, org = actors
    if verified:
        approve(client, actors, submit(client, actors).json()["id"])
    maker = people["maker"]["headers"]
    checker = people["approver"]["headers"]
    beneficiary = client.post(
        "/api/v1/beneficiaries",
        headers=maker,
        json={"name": "Supplier", "bank_code": bank_code, "account_number": "123456789"},
    )
    assert beneficiary.status_code == 201
    payment = client.post(
        "/api/v1/payment-requests",
        headers=maker,
        json={
            "invoice_reference": "OPS-INV-1",
            "amount_minor": 5_000_000,
            "currency": "VND",
            "beneficiary_id": beneficiary.json()["id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert payment.status_code == 201
    payment_id = payment.json()["id"]
    assert (
        client.post(f"/api/v1/payment-requests/{payment_id}/submit", headers=maker).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/payment-requests/{payment_id}/approve", headers=checker, json={}
        ).status_code
        == 200
    )
    response = client.post(f"/api/v1/payment-requests/{payment_id}/sign", headers=checker, json={})
    assert response.status_code == 200, response.text
    return response.json()


def create_transfer(client, actors, payment, key="transfer-key-001", actor="approver", **extra):
    people, _ = actors
    return client.post(
        "/api/v1/transfers",
        headers={**people[actor]["headers"], "Idempotency-Key": key},
        json={"payment_request_id": payment["id"], **extra},
    )


def test_verification_submission_and_independent_review(client, db_session, actors):
    people, org = actors
    submission = submit(client, actors).json()
    assert "document_object_key" not in submission
    assert "submitted_by" not in submission
    assert (
        submission["document_sha256"]
        == hashlib.sha256(b"%PDF-1.7 test business evidence").hexdigest()
    )
    submit(client, actors, expected=409)
    assert (
        client.patch(
            f"/api/v1/organizations/{org.id}",
            headers=people["maker"]["headers"],
            json={"name": "Changed"},
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/organizations/{org.id}/verification", headers=people["outsider"]["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/platform/verifications", headers=people["maker"]["headers"]).status_code
        == 403
    )
    queue = client.get("/api/v1/platform/verifications", headers=people["reviewer"]["headers"])
    assert queue.status_code == 200 and len(queue.json()) == 1
    document = client.get(
        f"/api/v1/platform/verifications/{submission['id']}/document",
        headers=people["reviewer"]["headers"],
    )
    assert document.status_code == 200 and "attachment" in document.headers["Content-Disposition"]
    assert document.headers["Cache-Control"] == "no-store"
    assert (
        client.get(
            f"/api/v1/platform/verifications/{submission['id']}/document",
            headers=people["maker"]["headers"],
        ).status_code
        == 403
    )
    approve(client, actors, submission["id"])
    result = client.get(
        f"/api/v1/organizations/{org.id}", headers=people["maker"]["headers"]
    ).json()
    assert result["verification_status"] == "APPROVED"
    assert result["verification_method"] == "MANUAL_REVIEW" and result["verification_level"] == 2
    submit(client, actors, expected=409)


def test_reviewer_self_review_and_missing_checks_are_blocked(client, db_session, actors):
    people, org = actors
    submission = submit(client, actors).json()
    body = {
        "decision": "APPROVED",
        "reason": "Independent check evidence with a detailed explanation.",
    }
    reviewer = people["reviewer"]["headers"]
    path = f"/api/v1/platform/verifications/{submission['id']}/review"
    assert client.post(path, headers=reviewer, json=body).status_code == 422
    db_session.add(
        Membership(organization_id=org.id, user_id=people["reviewer"]["user"].id, role=Role.VIEWER)
    )
    db_session.commit()
    assert client.get("/api/v1/platform/verifications", headers=reviewer).json() == []
    assert client.post(path, headers=reviewer, json=body).status_code == 403
    assert (
        client.get(
            f"/api/v1/platform/verifications/{submission['id']}/document", headers=reviewer
        ).status_code
        == 403
    )


def test_verification_changes_requested_allows_resubmission(client, actors):
    people, _ = actors
    submission = submit(client, actors).json()
    response = client.post(
        f"/api/v1/platform/verifications/{submission['id']}/review",
        headers=people["reviewer"]["headers"],
        json={
            "decision": "CHANGES_REQUESTED",
            "reason": "Please provide a signed document proving authority to represent the business.",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CHANGES_REQUESTED"
    replacement = submit(client, actors).json()
    assert replacement["id"] != submission["id"]
    approve(client, actors, replacement["id"])
    assert (
        client.post(
            f"/api/v1/platform/verifications/{submission['id']}/review",
            headers=people["reviewer"]["headers"],
            json={
                "decision": "REJECTED",
                "reason": "Cannot review the same submission a second time.",
            },
        ).status_code
        == 409
    )


def test_verification_expiry_and_profile_changes_invalidate_trust(client, db_session, actors):
    people, org = actors
    submission = submit(client, actors).json()
    approve(client, actors, submission["id"])
    item = db_session.get(BusinessVerification, uuid.UUID(submission["id"]))
    item.valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    path = f"/api/v1/organizations/{org.id}"
    result = client.get(path, headers=people["maker"]["headers"]).json()
    assert result["verification_status"] == "EXPIRED" and result["verification_level"] == 0
    item.valid_until = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    result = client.patch(
        path, headers=people["maker"]["headers"], json={"name": "New Legal Identity"}
    )
    assert result.status_code == 200
    assert result.json()["verification_status"] == "STALE"
    assert result.json()["verification_level"] == 0


def test_verification_rejects_invalid_and_oversize_documents(client, actors, monkeypatch):
    submit(client, actors, content=b"not a PDF", expected=415)
    monkeypatch.setattr(settings, "max_business_document_bytes", 8)
    submit(client, actors, expected=413)


def test_document_tampering_and_reviewer_mfa_are_blocked(client, db_session, actors):
    people, _ = actors
    submission = submit(client, actors).json()
    item = db_session.get(BusinessVerification, uuid.UUID(submission["id"]))
    FakeStorage.objects[item.document_object_key] += b"tampered"
    assert (
        client.get(
            f"/api/v1/platform/verifications/{item.id}/document",
            headers=people["reviewer"]["headers"],
        ).status_code
        == 409
    )
    people["reviewer"]["user"].mfa_enabled = False
    db_session.commit()
    assert (
        client.get(
            "/api/v1/platform/verifications", headers=people["reviewer"]["headers"]
        ).status_code
        == 403
    )


def test_transfer_idempotency_and_signed_snapshot(client, db_session, actors):
    payment = signed_payment(client, actors)
    # Alter unrelated mutable display fields: outgoing instruction still uses the signed manifest.
    version = db_session.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == uuid.UUID(payment["id"])
        )
    )
    version.amount_minor = 999_999
    version.bank_code = "FAKEBANK"
    db_session.commit()
    first = create_transfer(client, actors, payment)
    assert first.status_code == 201, first.text
    item = first.json()
    assert item["amount_minor"] == 5_000_000 and item["bank_code"] == "VCB"
    assert "account_number" not in item and "account_ciphertext" not in item
    duplicate = create_transfer(client, actors, payment)
    another_key = create_transfer(client, actors, payment, key="another-transfer-key")
    assert duplicate.json()["id"] == another_key.json()["id"] == item["id"]
    assert db_session.scalar(select(func.count()).select_from(Transfer)) == 1
    assert db_session.scalar(select(func.count()).select_from(SandboxReceipt)) == 1
    wrong_payment = {**payment, "id": str(uuid.uuid4())}
    assert create_transfer(client, actors, wrong_payment).status_code == 409
    extra_fields = create_transfer(
        client, actors, payment, key="tamper-attempt-key", amount_minor=1
    )
    assert extra_fields.status_code == 422


def test_transfer_requires_verified_business_and_not_demo_seed(client, db_session, actors):
    payment = signed_payment(client, actors, verified=False)
    assert create_transfer(client, actors, payment).status_code == 409
    _, org = actors
    org.verification_level = 2
    db_session.commit()
    assert create_transfer(client, actors, payment).status_code == 409
    public_token = payment["public_url"].rsplit("/", 1)[-1]
    result = client.get("/api/v1/public/verify/" + public_token).json()
    assert result["organization"]["verification_status"] == "DEMO_SEEDED"
    assert result["warnings"]


def test_transfer_requires_mfa_independent_actor_and_tenant_access(client, db_session, actors):
    people, _ = actors
    payment = signed_payment(client, actors)
    assert create_transfer(client, actors, payment, actor="maker").status_code == 403
    assert create_transfer(client, actors, payment, actor="outsider").status_code == 404
    people["approver"]["user"].mfa_verified_at = None
    db_session.commit()
    assert create_transfer(client, actors, payment).status_code == 403
    code = pyotp.TOTP(people["approver"]["secret"]).now()
    assert create_transfer(client, actors, payment, totp_code=code).status_code == 201
    # A stale verification timestamp must not bypass disabled MFA.
    people["approver"]["user"].mfa_enabled = False
    people["approver"]["user"].mfa_verified_at = datetime.now(timezone.utc)
    db_session.commit()
    assert create_transfer(client, actors, payment, key="new-key-disabled-mfa").status_code == 403


@pytest.mark.parametrize("mode", ["live", "disabled"])
def test_live_and_disabled_transfer_modes_fail_closed(
    client, db_session, actors, monkeypatch, mode
):
    payment = signed_payment(client, actors)
    monkeypatch.setattr(settings, "transfer_mode", mode)
    assert create_transfer(client, actors, payment).status_code == 503
    assert db_session.scalar(select(func.count()).select_from(Transfer)) == 0
    assert db_session.scalar(select(func.count()).select_from(SandboxReceipt)) == 0


def test_transfer_reconciliation_recovers_missing_event(client, db_session, actors):
    people, _ = actors
    payment = signed_payment(client, actors)
    item = create_transfer(client, actors, payment).json()
    path = "/api/v1/transfers/" + item["id"]
    response = client.post(
        path + "/sandbox-outcome",
        headers=people["approver"]["headers"],
        json={"status": "SUCCEEDED", "deliver_event": False},
    )
    assert response.status_code == 200 and response.json()["status"] == "SUBMITTED"
    result = client.post(path + "/reconcile", headers=people["approver"]["headers"])
    assert result.status_code == 200 and result.json()["status"] == "SUCCEEDED"
    assert result.json()["reconciled_at"]
    assert (
        client.post(path + "/reconcile", headers=people["outsider"]["headers"]).status_code == 404
    )
    assert (
        client.post(
            path + "/sandbox-outcome",
            headers=people["approver"]["headers"],
            json={"status": "FAILED"},
        ).status_code
        == 409
    )


def test_revoked_and_expired_payments_cannot_create_transfers(client, db_session, actors):
    people, _ = actors
    payment = signed_payment(client, actors)
    version = db_session.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == uuid.UUID(payment["id"])
        )
    )
    version.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert create_transfer(client, actors, payment).status_code == 409
    version.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    assert (
        client.post(
            "/api/v1/payment-requests/" + payment["id"] + "/revoke",
            headers=people["approver"]["headers"],
            json={"reason": "Invoice cancelled"},
        ).status_code
        == 200
    )
    assert create_transfer(client, actors, payment).status_code == 409


def test_webhook_signatures_replays_and_amount_binding(client, db_session, actors, monkeypatch):
    payment = signed_payment(client, actors)
    item = create_transfer(client, actors, payment).json()
    secret = "test-webhook-secret-more-than-32-bytes-long"
    monkeypatch.setattr(settings, "transfer_webhook_secret", secret)
    body = {
        "event_id": str(uuid.uuid4()),
        "provider_reference": item["provider_reference"],
        "status": "SUCCEEDED",
        "amount_minor": item["amount_minor"],
        "currency": "VND",
    }

    def deliver(payload=body, timestamp=None, signature=None):
        timestamp = timestamp or str(int(time.time()))
        raw = json.dumps(payload).encode()
        digest = hmac.new(
            secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        return client.post(
            "/api/v1/transfers/webhooks/sandbox",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-PaySeal-Timestamp": timestamp,
                "X-PaySeal-Signature": signature or digest,
            },
        )

    assert deliver(signature="forged").status_code == 401
    assert deliver(timestamp=str(int(time.time()) - 600)).status_code == 401
    assert deliver({**body, "amount_minor": 1}).status_code == 409
    assert db_session.get(Transfer, uuid.UUID(item["id"])).status == "SUBMITTED"
    assert deliver().json() == {"received": True, "duplicate": False}
    assert deliver().json() == {"received": True, "duplicate": True}
    assert db_session.scalar(select(func.count()).select_from(TransferEvent)) == 1
    assert deliver({**body, "status": "FAILED"}).status_code == 409
    assert deliver({**body, "event_id": str(uuid.uuid4()), "status": "FAILED"}).status_code == 409
    assert db_session.get(Transfer, uuid.UUID(item["id"])).status == "SUCCEEDED"


def test_webhook_disabled_without_secret(client, actors, monkeypatch):
    monkeypatch.setattr(settings, "transfer_webhook_secret", "")
    assert client.post("/api/v1/transfers/webhooks/sandbox", json={}).status_code == 503


def test_revoking_business_verification_blocks_new_transfers(client, actors):
    people, org = actors
    payment = signed_payment(client, actors)
    history = client.get(
        f"/api/v1/organizations/{org.id}/verification", headers=people["maker"]["headers"]
    ).json()
    result = client.post(
        f"/api/v1/platform/verifications/{history[0]['id']}/revoke",
        headers=people["reviewer"]["headers"],
        json={
            "reason": "Independent evidence confirms the representative is no longer authorized."
        },
    )
    assert result.status_code == 200 and result.json()["status"] == "REVOKED"
    assert create_transfer(client, actors, payment).status_code == 409
    assert (
        client.get(f"/api/v1/organizations/{org.id}", headers=people["maker"]["headers"]).json()[
            "verification_level"
        ]
        == 0
    )


def test_public_issuer_identity_stays_bound_to_signed_snapshot(client, actors):
    people, org = actors
    payment = signed_payment(client, actors)
    client.patch(
        f"/api/v1/organizations/{org.id}",
        headers=people["maker"]["headers"],
        json={"name": "Changed Identity"},
    )
    result = client.get("/api/v1/public/verify/" + payment["public_url"].rsplit("/", 1)[-1]).json()
    assert result["organization"]["name"] == "Operations Ltd"
    assert result["organization"]["verification_status"] == "STALE"
    assert result["organization"]["verification_level"] == 0
    client.patch(
        f"/api/v1/organizations/{org.id}",
        headers=people["maker"]["headers"],
        json={"name": "Operations Ltd"},
    )
    assert (
        client.get(f"/api/v1/organizations/{org.id}", headers=people["maker"]["headers"]).json()[
            "verification_status"
        ]
        == "STALE"
    )


def test_supplied_incorrect_mfa_is_not_ignored_even_with_recent_verification(client, actors):
    people, _ = actors
    payment = signed_payment(client, actors)
    totp = pyotp.TOTP(people["approver"]["secret"])
    valid = {totp.at(time.time() + offset) for offset in (-30, 0, 30)}
    wrong = next(f"{n:06d}" for n in range(10) if f"{n:06d}" not in valid)
    assert create_transfer(client, actors, payment, totp_code=wrong).status_code == 401
