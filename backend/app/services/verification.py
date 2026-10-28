from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto.canonical import canonicalize, sha256_hex
from app.crypto.jws import jwk_to_public_key, verify_compact
from app.models.entities import (
    KeyStatus,
    Organization,
    OrganizationCertificate,
    OrganizationKey,
    PaymentRequest,
    PaymentRequestVersion,
    PaymentStatus,
)
from app.services.business_verification import verification_state
from app.services.runtime import encryption_service, root_authority


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def find_public_payment(db: Session, token: str) -> PaymentRequest | None:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return db.scalar(select(PaymentRequest).where(PaymentRequest.public_token_hash == digest))


def verify_payment(db: Session, payment: PaymentRequest) -> dict:
    now = datetime.now(timezone.utc)
    version = db.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == payment.id,
            PaymentRequestVersion.version == payment.current_version,
        )
    )
    organization = db.get(Organization, payment.organization_id)
    key = db.scalar(
        select(OrganizationKey).where(
            OrganizationKey.kid == payment.signature_kid,
            OrganizationKey.organization_id == payment.organization_id,
        )
    )
    base = {
        "status": "INVALID_SIGNATURE",
        "signature_valid": False,
        "issuer_verified": False,
        "document_status": "UNKNOWN",
        "expired": False,
        "revoked": False,
        "superseded": False,
        "organization": None,
        "payment": None,
        "issued_at": payment.signed_at,
        "expires_at": version.expires_at if version else None,
        "warnings": [],
    }
    if not all([version, organization, key, payment.signed_jws]):
        base["status"] = "UNKNOWN_ISSUER" if key is None else "INVALID_SIGNATURE"
        return base
    cert = db.scalar(
        select(OrganizationCertificate).where(OrganizationCertificate.key_id == key.id)
    )
    if cert is None:
        base["status"] = "CERTIFICATE_INVALID"
        return base
    try:
        _, cert_payload = verify_compact(
            cert.signature_jws, root_authority().public_key(), "payseal-certificate+jws"
        )
        if (
            canonicalize(cert_payload) != canonicalize(cert.payload_json)
            or cert_payload.get("kid") != key.kid
        ):
            raise ValueError("certificate payload mismatch")
        if now < _aware(cert.valid_from) or now > _aware(cert.valid_to):
            raise ValueError("certificate outside validity")
        base["issuer_verified"] = True
    except (ValueError, InvalidSignature, TypeError, KeyError):
        base["status"] = "CERTIFICATE_INVALID"
        return base
    try:
        header, payload = verify_compact(
            payment.signed_jws, jwk_to_public_key(key.public_key_jwk), "payseal+jws"
        )
        if (
            header.get("kid") != key.kid
            or canonicalize(payload) != canonicalize(version.payload_json)
            or sha256_hex(canonicalize(payload)) != version.payload_hash
        ):
            raise ValueError("signed payload mismatch")
        base["signature_valid"] = True
    except (ValueError, InvalidSignature, TypeError, KeyError):
        return base
    if key.status == KeyStatus.REVOKED:
        base["status"] = "KEY_REVOKED"
    elif (
        key.status == KeyStatus.COMPROMISED
        and key.compromised_at
        and payment.signed_at
        and _aware(payment.signed_at) >= _aware(key.compromised_at)
    ):
        base["status"] = "KEY_COMPROMISED"
    elif key.status == KeyStatus.COMPROMISED:
        base["warnings"].append("Key was compromised after this signature was created")
    account = payload["beneficiary"]["account_number"]
    trust = verification_state(db, organization)
    base["organization"] = {
        "name": payload["organization"]["name"],
        "tax_id": payload["organization"]["tax_id"],
        "domain": cert_payload["domain"],
        **trust,
        "verification_level": min(
            int(cert_payload.get("assurance_level", 0)), trust["verification_level"]
        ),
        "signed_verification_level": cert_payload.get("assurance_level", 0),
        "signed_verification_method": cert_payload.get("assurance_method"),
    }
    if trust["verification_status"] == "DEMO_SEEDED":
        base["warnings"].append(
            "Doanh nghiệp demo: mức xác thực được tạo từ dữ liệu mẫu, không phải hồ sơ đã xét duyệt."
        )
    elif trust["verification_status"] != "APPROVED":
        base["warnings"].append(
            "Chữ ký hợp lệ không đồng nghĩa doanh nghiệp đã được xác minh. Cần kiểm tra độc lập trước khi thanh toán."
        )
    base["payment"] = {
        "amount_minor": payload["payment"]["amount_minor"],
        "currency": payload["payment"]["currency"],
        "beneficiary": payload["beneficiary"]["name"],
        "bank_code": payload["beneficiary"]["bank_code"],
        "account_masked": encryption_service().mask(account),
        "invoice_reference": payload["invoice"]["reference"],
    }
    base["revoked"] = payment.status == PaymentStatus.REVOKED
    base["superseded"] = payment.status == PaymentStatus.SUPERSEDED
    signed_expiry = _aware(datetime.fromisoformat(payload["expires_at"]))
    # A local restriction may shorten validity, but can never extend the signed deadline.
    effective_expiry = min(signed_expiry, _aware(version.expires_at))
    base["expires_at"] = effective_expiry
    base["expired"] = now >= effective_expiry or payment.status == PaymentStatus.EXPIRED
    if base["status"] in {"KEY_REVOKED", "KEY_COMPROMISED"}:
        return base
    if base["revoked"]:
        base["status"] = "REVOKED"
    elif base["superseded"]:
        base["status"] = "SUPERSEDED"
    elif base["expired"]:
        base["status"] = "EXPIRED"
    else:
        base["status"] = "VERIFIED"
    return base


def verify_document(db: Session, payment: PaymentRequest, data: bytes) -> dict[str, str]:
    result = verify_payment(db, payment)
    version = db.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == payment.id,
            PaymentRequestVersion.version == payment.current_version,
        )
    )
    match = bool(
        version and version.document_sha256 and sha256_hex(data) == version.document_sha256
    )
    return {
        "payment_signature": "VERIFIED"
        if result["signature_valid"] and result["issuer_verified"]
        else "INVALID",
        "document_integrity": "MATCH" if match else "MISMATCH",
        "status": result["status"] if match else "DOCUMENT_MISMATCH",
    }
