from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, require_roles, tenant_context
from app.core.database import get_db
from app.crypto.canonical import canonicalize, sha256_hex
from app.models.entities import (
    IdempotencyRecord,
    KeyStatus,
    OrganizationKey,
    PaymentRequest,
    PaymentStatus,
    Role,
)
from app.schemas.api import (
    DecisionRequest,
    PaymentCreate,
    PaymentPatch,
    PaymentResponse,
    RevokeRequest,
)
from app.services.audit import add_audit_event
from app.services.documents import MinioStorage
from app.services.payments import (
    approve_payment,
    create_payment,
    reject_payment,
    sign_payment,
    submit_payment,
    transition,
    update_payment,
)
from app.services.serializers import payment_dict

router = APIRouter(prefix="/payment-requests", tags=["Payment requests"])


def _get_locked(db: Session, organization_id: uuid.UUID, payment_id: uuid.UUID) -> PaymentRequest:
    payment = db.scalar(
        select(PaymentRequest)
        .where(
            PaymentRequest.id == payment_id,
            PaymentRequest.organization_id == organization_id,
        )
        .with_for_update()
    )
    if payment is None:
        raise HTTPException(404, "Payment request not found")
    return payment


def _idempotent(
    db: Session,
    context: TenantContext,
    operation: str,
    key: str | None,
    request_hash: str,
) -> PaymentRequest | None:
    if not key:
        return None
    if len(key) > 128:
        raise HTTPException(422, "Idempotency-Key is too long")
    record = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == context.organization_id,
            IdempotencyRecord.actor_id == context.user.id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if record:
        if record.request_hash != request_hash:
            raise HTTPException(409, "Idempotency key was reused with a different request")
        return db.scalar(
            select(PaymentRequest).where(
                PaymentRequest.id == record.resource_id,
                PaymentRequest.organization_id == context.organization_id,
            )
        )
    return None


@router.post("", response_model=PaymentResponse, status_code=201)
def create(
    data: PaymentCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    digest = sha256_hex(canonicalize(data.model_dump(mode="json")))
    existing = _idempotent(db, context, "CREATE_PAYMENT", idempotency_key, digest)
    if existing:
        return payment_dict(db, existing)
    payment = create_payment(db, context.organization_id, context.user, data)
    if idempotency_key:
        db.add(
            IdempotencyRecord(
                organization_id=context.organization_id,
                actor_id=context.user.id,
                operation="CREATE_PAYMENT",
                key=idempotency_key,
                request_hash=digest,
                resource_id=payment.id,
            )
        )
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="CREATE_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={
            "invoice_reference": data.invoice_reference,
            "amount_minor": data.amount_minor,
            "currency": data.currency,
        },
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.get("", response_model=list[PaymentResponse])
def list_payments(context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)):
    values = db.scalars(
        select(PaymentRequest)
        .where(PaymentRequest.organization_id == context.organization_id)
        .order_by(PaymentRequest.created_at.desc())
    ).all()
    return [payment_dict(db, item) for item in values]


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: uuid.UUID,
    context: TenantContext = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    return payment_dict(db, payment)


@router.patch("/{payment_id}", response_model=PaymentResponse)
def patch_payment(
    payment_id: uuid.UUID,
    data: PaymentPatch,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    if payment.maker_id != context.user.id and context.membership.role != Role.OWNER:
        raise HTTPException(403, "Only the maker or owner can edit this draft")
    update_payment(db, payment, data)
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="UPDATE_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"fields": list(data.model_dump(exclude_unset=True))},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.post("/{payment_id}/submit", response_model=PaymentResponse)
def submit(
    payment_id: uuid.UUID,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    if payment.maker_id != context.user.id and context.membership.role != Role.OWNER:
        raise HTTPException(403, "Only the maker or owner can submit")
    submit_payment(db, payment)
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="SUBMIT_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.post("/{payment_id}/approve", response_model=PaymentResponse)
def approve(
    payment_id: uuid.UUID,
    data: DecisionRequest,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    approve_payment(db, payment, context.user, data.comment, data.totp_code)
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="APPROVE_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"comment": data.comment},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.post("/{payment_id}/reject", response_model=PaymentResponse)
def reject(
    payment_id: uuid.UUID,
    data: DecisionRequest,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    reject_payment(db, payment, context.user, data.comment)
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="REJECT_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"comment": data.comment},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.post("/{payment_id}/sign", response_model=PaymentResponse)
def sign(
    payment_id: uuid.UUID,
    data: DecisionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    digest = sha256_hex(canonicalize({"payment_id": str(payment_id)}))
    existing = _idempotent(db, context, "SIGN_PAYMENT", idempotency_key, digest)
    if existing:
        return payment_dict(db, existing)
    payment = _get_locked(db, context.organization_id, payment_id)
    active_key_existed = (
        db.scalar(
            select(OrganizationKey.id).where(
                OrganizationKey.organization_id == context.organization_id,
                OrganizationKey.status == KeyStatus.ACTIVE,
            )
        )
        is not None
    )
    sign_payment(db, payment, context.user, data.totp_code)
    if idempotency_key:
        db.add(
            IdempotencyRecord(
                organization_id=context.organization_id,
                actor_id=context.user.id,
                operation="SIGN_PAYMENT",
                key=idempotency_key,
                request_hash=digest,
                resource_id=payment.id,
            )
        )
    if not active_key_existed:
        add_audit_event(
            db,
            organization_id=context.organization_id,
            actor_id=context.user.id,
            event_type="CREATE_KEY",
            object_type="organization_key",
            object_id=payment.signature_kid or "unknown",
            data={"kid": payment.signature_kid, "algorithm": payment.algorithm},
            correlation_id=request.state.correlation_id,
        )
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="SIGN_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"kid": payment.signature_kid},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.post("/{payment_id}/revoke", response_model=PaymentResponse)
def revoke(
    payment_id: uuid.UUID,
    data: RevokeRequest,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    transition(payment, PaymentStatus.REVOKED)
    payment.revoked_at, payment.revocation_reason = (
        datetime.now(timezone.utc),
        data.reason,
    )
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="REVOKE_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"reason": data.reason},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return payment_dict(db, payment)


@router.get("/{payment_id}/pdf")
def download_pdf(
    payment_id: uuid.UUID,
    context: TenantContext = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    payment = _get_locked(db, context.organization_id, payment_id)
    if not payment.document_object_key:
        raise HTTPException(409, "Payment has no signed PDF")
    data = MinioStorage().get_pdf(payment.document_object_key)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="payseal-{payment.id}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
