import hashlib
import hmac
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, require_roles, tenant_context
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import PaymentRequest, Role, SandboxReceipt, Transfer, TransferEvent
from app.schemas.operations import (
    SandboxOutcome,
    TransferCreate,
    TransferDispatch,
    TransferResponse,
    TransferWebhook,
)
from app.services.audit import add_audit_event
from app.services.live_payments import (
    active_channel,
    dispatch_transfer,
    fresh_mfa,
    reconcile_live_transfer,
)
from app.services.payos_gateway import live_blockers
from app.services.transfer_provider import ProviderReceipt, transfer_provider
from app.services.transfers import apply_receipt, create_transfer

router = APIRouter(prefix="/transfers", tags=["Transfers"])


def audit(db: Session, request: Request, item: Transfer, event: str, actor_id: uuid.UUID | None):
    add_audit_event(
        db,
        organization_id=item.organization_id,
        actor_id=actor_id,
        event_type=event,
        object_type="transfer",
        object_id=str(item.id),
        data={
            "status": item.status,
            "provider": item.provider,
            "amount_minor": item.amount_minor,
            "currency": item.currency,
        },
        correlation_id=request.state.correlation_id,
    )


def locked(db: Session, context: TenantContext, transfer_id: uuid.UUID) -> Transfer:
    item = db.scalar(
        select(Transfer)
        .where(Transfer.id == transfer_id, Transfer.organization_id == context.organization_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Transfer not found")
    return item


@router.get("/capabilities")
def capabilities(context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)):
    connected = False
    try:
        active_channel(db, context.organization_id, "PAYOUT")
        connected = True
    except HTTPException:
        pass
    return {
        "mode": settings.transfer_mode,
        "real_money_enabled": settings.transfer_mode == "live"
        and not live_blockers()
        and connected,
        "safety_limit": settings.max_live_transfer_amount,
        "currencies": ["VND"],
        "webhook_configured": bool(settings.transfer_webhook_secret),
    }


@router.get("", response_model=list[TransferResponse])
def history(context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)):
    return db.scalars(
        select(Transfer)
        .where(Transfer.organization_id == context.organization_id)
        .order_by(Transfer.created_at.desc())
        .limit(200)
    ).all()


@router.post("", response_model=TransferResponse, status_code=201)
def create(
    data: TransferCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    item, created = create_transfer(
        db, context, data.payment_request_id, idempotency_key, data.totp_code, data.confirm_live
    )
    if created:
        audit(
            db,
            request,
            item,
            "QUEUE_LIVE_TRANSFER" if item.provider == "payos" else "CREATE_SANDBOX_TRANSFER",
            context.user.id,
        )
    db.commit()
    if created and item.provider == "payos":
        item = dispatch_transfer(
            db, item.id, context.organization_id, context.user.id, request.state.correlation_id
        )
    return item


@router.post("/{transfer_id}/reconcile", response_model=TransferResponse)
def reconcile(
    transfer_id: uuid.UUID,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(Transfer).where(
            Transfer.id == transfer_id, Transfer.organization_id == context.organization_id
        )
    )
    if item is None:
        raise HTTPException(404, "Transfer not found")
    if item.provider == "payos":
        return reconcile_live_transfer(db, item, context.user.id, request.state.correlation_id)
    item = locked(db, context, transfer_id)
    receipt = transfer_provider(db).lookup(item.provider_reference)
    apply_receipt(item, receipt)
    item.reconciled_at = datetime.now(timezone.utc)
    audit(db, request, item, "RECONCILE_TRANSFER", context.user.id)
    db.commit()
    return item


@router.post("/{transfer_id}/dispatch", response_model=TransferResponse)
def dispatch(
    transfer_id: uuid.UUID,
    data: TransferDispatch,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(Transfer).where(
            Transfer.id == transfer_id, Transfer.organization_id == context.organization_id
        )
    )
    if item is None:
        raise HTTPException(404, "Transfer not found")
    if db.get(PaymentRequest, item.payment_request_id).maker_id == context.user.id:
        raise HTTPException(403, "Maker cannot initiate their own transfer")
    fresh_mfa(context, data.totp_code)
    return dispatch_transfer(
        db, item.id, context.organization_id, context.user.id, request.state.correlation_id
    )


@router.post("/{transfer_id}/sandbox-outcome", response_model=TransferResponse)
def simulate(
    transfer_id: uuid.UUID,
    data: SandboxOutcome,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    transfer_provider(db)
    item = locked(db, context, transfer_id)
    record = db.scalar(
        select(SandboxReceipt)
        .where(SandboxReceipt.provider_reference == item.provider_reference)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(409, "Provider receipt not found")
    if record.status not in {"PENDING", data.status}:
        raise HTTPException(409, "Terminal transfer outcome cannot be changed")
    record.status, record.updated_at = data.status, datetime.now(timezone.utc)
    if data.deliver_event:
        apply_receipt(
            item,
            ProviderReceipt(
                record.provider_reference, record.status, record.amount_minor, record.currency
            ),
        )
    audit(db, request, item, "SIMULATE_PROVIDER_OUTCOME", context.user.id)
    db.commit()
    return item


@router.post("/webhooks/sandbox")
async def webhook(
    request: Request,
    x_payseal_timestamp: str = Header(default=""),
    x_payseal_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    transfer_provider(db)
    secret = settings.transfer_webhook_secret
    if not secret:
        raise HTTPException(503, "Transfer webhook is not configured")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 16_384:
            raise HTTPException(413, "Webhook payload is too large")
    try:
        fresh = abs(time.time() - int(x_payseal_timestamp)) <= 300
    except ValueError:
        fresh = False
    expected = hmac.new(
        secret.encode(), x_payseal_timestamp.encode() + b"." + bytes(raw), hashlib.sha256
    ).hexdigest()
    if not fresh or not hmac.compare_digest(expected, x_payseal_signature):
        raise HTTPException(401, "Invalid webhook signature or timestamp")
    try:
        data = TransferWebhook.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid webhook payload") from None
    item = db.scalar(
        select(Transfer)
        .where(
            Transfer.provider_reference == data.provider_reference, Transfer.provider == "sandbox"
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Transfer not found")
    digest = hashlib.sha256(raw).hexdigest()
    previous = db.get(TransferEvent, data.event_id)
    if previous:
        if previous.transfer_id != item.id or previous.payload_hash != digest:
            raise HTTPException(409, "Webhook event ID was reused")
        return {"received": True, "duplicate": True}
    receipt = ProviderReceipt(
        data.provider_reference, data.status, data.amount_minor, data.currency
    )
    record = db.scalar(
        select(SandboxReceipt)
        .where(SandboxReceipt.provider_reference == item.provider_reference)
        .with_for_update()
    )
    if record is None or record.status not in {"PENDING", data.status}:
        raise HTTPException(409, "Provider ledger conflict")
    apply_receipt(item, receipt)
    record.status, record.updated_at = data.status, datetime.now(timezone.utc)
    db.add(
        TransferEvent(
            id=data.event_id, transfer_id=item.id, payload_hash=digest, status=data.status
        )
    )
    try:
        db.flush()
    except IntegrityError:
        # A concurrent delivery may use this event ID for another transfer.
        db.rollback()
        raise HTTPException(409, "Webhook event ID was reused") from None
    audit(db, request, item, "TRANSFER_WEBHOOK", None)
    db.commit()
    return {"received": True, "duplicate": False}
