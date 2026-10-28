from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import pyotp
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crypto.canonical import canonicalize, sha256_hex
from app.crypto.jws import sign_compact
from app.models.entities import (
    Approval,
    Beneficiary,
    Organization,
    PaymentRequest,
    PaymentRequestVersion,
    PaymentStatus,
    User,
)
from app.schemas.api import PaymentCreate, PaymentPatch
from app.services.documents import MinioStorage, render_payment_pdf
from app.services.keys import get_or_create_active_key
from app.services.policy import ApprovalPolicy
from app.services.runtime import encryption_service, signing_provider

TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.DRAFT: {PaymentStatus.PENDING_APPROVAL},
    PaymentStatus.PENDING_APPROVAL: {PaymentStatus.APPROVED, PaymentStatus.REJECTED},
    PaymentStatus.APPROVED: {PaymentStatus.SIGNED},
    PaymentStatus.SIGNED: {
        PaymentStatus.REVOKED,
        PaymentStatus.EXPIRED,
        PaymentStatus.SUPERSEDED,
    },
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def transition(payment: PaymentRequest, target: PaymentStatus) -> None:
    if target not in TRANSITIONS.get(payment.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition {payment.status.value} -> {target.value}",
        )
    payment.status = target


def current_version(db: Session, payment: PaymentRequest) -> PaymentRequestVersion:
    version = db.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == payment.id,
            PaymentRequestVersion.version == payment.current_version,
        )
    )
    if version is None:
        raise RuntimeError("payment version missing")
    return version


def create_payment(
    db: Session, organization_id: uuid.UUID, maker: User, data: PaymentCreate
) -> PaymentRequest:
    if _aware(data.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(422, "expires_at must be in the future")
    beneficiary = db.scalar(
        select(Beneficiary).where(
            Beneficiary.id == data.beneficiary_id,
            Beneficiary.organization_id == organization_id,
        )
    )
    if beneficiary is None:
        raise HTTPException(404, "Beneficiary not found")
    payment = PaymentRequest(organization_id=organization_id, maker_id=maker.id)
    db.add(payment)
    db.flush()
    version = PaymentRequestVersion(
        payment_request_id=payment.id,
        version=1,
        invoice_reference=data.invoice_reference,
        currency=data.currency,
        amount_minor=data.amount_minor,
        beneficiary_id=beneficiary.id,
        beneficiary_name=beneficiary.name,
        bank_code=beneficiary.bank_code,
        account_ciphertext=beneficiary.account_ciphertext,
        account_last4=beneficiary.account_last4,
        note=data.note,
        expires_at=_aware(data.expires_at),
        nonce=secrets.token_urlsafe(24),
    )
    db.add(version)
    db.flush()
    return payment


def update_payment(db: Session, payment: PaymentRequest, data: PaymentPatch) -> PaymentRequest:
    if payment.status != PaymentStatus.DRAFT:
        raise HTTPException(409, "Only draft payments can be edited")
    version = current_version(db, payment)
    values = data.model_dump(exclude_unset=True)
    if "beneficiary_id" in values:
        beneficiary = db.scalar(
            select(Beneficiary).where(
                Beneficiary.id == values.pop("beneficiary_id"),
                Beneficiary.organization_id == payment.organization_id,
            )
        )
        if beneficiary is None:
            raise HTTPException(404, "Beneficiary not found")
        version.beneficiary_id, version.beneficiary_name, version.bank_code = (
            beneficiary.id,
            beneficiary.name,
            beneficiary.bank_code,
        )
        version.account_ciphertext, version.account_last4 = (
            beneficiary.account_ciphertext,
            beneficiary.account_last4,
        )
    for key, value in values.items():
        setattr(version, key, _aware(value) if key == "expires_at" else value)
    return payment


def submit_payment(db: Session, payment: PaymentRequest) -> PaymentRequest:
    version = current_version(db, payment)
    requirement = ApprovalPolicy().evaluate(version.amount_minor, version.currency)
    payment.approvals_required = requirement.approvers
    payment.recent_mfa_required = requirement.recent_mfa
    transition(payment, PaymentStatus.PENDING_APPROVAL)
    return payment


def _verify_recent_mfa(user: User, code: str | None) -> None:
    now = datetime.now(timezone.utc)
    if (
        not code
        and user.mfa_enabled
        and user.mfa_secret_ciphertext
        and user.mfa_verified_at
        and (now - _aware(user.mfa_verified_at)).total_seconds()
        <= settings.mfa_recent_window_seconds
    ):
        return
    if not user.mfa_enabled or not user.mfa_secret_ciphertext or not code:
        raise HTTPException(403, "Recent MFA verification required")
    secret = encryption_service().decrypt(user.mfa_secret_ciphertext, context=b"payseal-mfa-v1")
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise HTTPException(401, "Invalid MFA code")
    user.mfa_verified_at = now


def approve_payment(
    db: Session,
    payment: PaymentRequest,
    approver: User,
    comment: str | None,
    totp_code: str | None,
) -> PaymentRequest:
    if payment.status != PaymentStatus.PENDING_APPROVAL:
        raise HTTPException(409, "Payment is not pending approval")
    if payment.maker_id == approver.id:
        raise HTTPException(403, "Maker cannot approve their own payment")
    if payment.recent_mfa_required:
        _verify_recent_mfa(approver, totp_code)
    if db.scalar(
        select(Approval).where(
            Approval.payment_request_id == payment.id,
            Approval.approver_id == approver.id,
        )
    ):
        raise HTTPException(409, "Approver already decided")
    db.add(
        Approval(
            payment_request_id=payment.id,
            approver_id=approver.id,
            decision="APPROVED",
            comment=comment,
        )
    )
    db.flush()
    count = (
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.payment_request_id == payment.id,
                Approval.decision == "APPROVED",
            )
        )
        or 0
    )
    if count >= payment.approvals_required:
        transition(payment, PaymentStatus.APPROVED)
    return payment


def reject_payment(
    db: Session, payment: PaymentRequest, approver: User, comment: str | None
) -> PaymentRequest:
    if payment.status != PaymentStatus.PENDING_APPROVAL:
        raise HTTPException(409, "Payment is not pending approval")
    if payment.maker_id == approver.id:
        raise HTTPException(403, "Maker cannot reject their own payment")
    db.add(
        Approval(
            payment_request_id=payment.id,
            approver_id=approver.id,
            decision="REJECTED",
            comment=comment,
        )
    )
    transition(payment, PaymentStatus.REJECTED)
    return payment


def sign_payment(
    db: Session,
    payment: PaymentRequest,
    signer: User,
    totp_code: str | None,
    storage: MinioStorage | None = None,
) -> PaymentRequest:
    if payment.status == PaymentStatus.SIGNED:
        return payment
    if payment.status != PaymentStatus.APPROVED:
        raise HTTPException(409, "Payment must be approved before signing")
    if payment.recent_mfa_required:
        _verify_recent_mfa(signer, totp_code)
    version = current_version(db, payment)
    organization = db.get(Organization, payment.organization_id)
    assert organization is not None
    key = get_or_create_active_key(db, organization)
    now = datetime.now(timezone.utc)
    public_token = secrets.token_urlsafe(32)
    payment.public_token = public_token
    payment.public_token_hash = hashlib.sha256(public_token.encode()).hexdigest()
    verification_url = f"{settings.public_verify_base_url.rstrip('/')}/{public_token}"
    account = encryption_service().decrypt(version.account_ciphertext)
    pdf = render_payment_pdf(
        organization=organization.name,
        invoice=version.invoice_reference,
        amount_minor=version.amount_minor,
        currency=version.currency,
        beneficiary=version.beneficiary_name,
        bank_code=version.bank_code,
        account_masked=encryption_service().mask(account),
        request_id=str(payment.id),
        verification_url=verification_url,
        issued_at=now,
    )
    version.document_sha256 = sha256_hex(pdf)
    version.issued_at = now
    payload = {
        "schema": "payseal.payment.v1",
        "request_id": str(payment.id),
        "version": version.version,
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "tax_id": organization.tax_id,
        },
        "payment": {"currency": version.currency, "amount_minor": version.amount_minor},
        "beneficiary": {
            "name": version.beneficiary_name,
            "bank_code": version.bank_code,
            "account_number": account,
        },
        "invoice": {
            "reference": version.invoice_reference,
            "document_sha256": version.document_sha256,
        },
        "issued_at": now.isoformat(),
        "expires_at": _aware(version.expires_at).isoformat(),
        "nonce": version.nonce,
    }
    version.payload_json = payload
    version.payload_hash = sha256_hex(canonicalize(payload))
    payment.signed_jws = sign_compact(
        payload,
        signing_provider().get_private_key(key.provider_key_id),
        key.kid,
        "payseal+jws",
    )
    payment.signature_kid, payment.algorithm, payment.signed_at = key.kid, "ES256", now
    object_key = f"{uuid.uuid4()}.pdf"
    (storage or MinioStorage()).put_pdf(object_key, pdf)
    payment.document_object_key = object_key
    transition(payment, PaymentStatus.SIGNED)
    return payment
