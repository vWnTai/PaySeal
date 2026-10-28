import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import TenantContext, require_roles, tenant_context
from app.core.database import get_db
from app.models.entities import Collection, PaymentChannel, Role
from app.schemas.operations import (
    ChannelConnect,
    ChannelResponse,
    CollectionCreate,
    CollectionResponse,
    VerificationRevocation,
)
from app.services.business_verification import verification_state
from app.services.live_payments import (
    connect_channel,
    create_receivable,
    fresh_mfa,
    lock_org,
    operation_audit,
    reconcile_receivable,
)
from app.services.payos_gateway import account_of, gateway, live_blockers

router = APIRouter(tags=["Payment integrations"])


@router.get("/payment-integrations/status")
def status(context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)):
    organization = lock_org(db, context.organization_id)
    channels = db.scalars(
        select(PaymentChannel).where(
            PaymentChannel.organization_id == organization.id, PaymentChannel.status == "ACTIVE"
        )
    ).all()
    state = verification_state(db, organization)["verification_status"]
    blockers = live_blockers()
    return {
        "provider": "payos",
        "infrastructure_ready": not blockers,
        "blockers": blockers,
        "business_verified": state == "APPROVED",
        "collection_connected": any(item.purpose == "COLLECTION" for item in channels),
        "payout_connected": any(item.purpose == "PAYOUT" for item in channels),
    }


@router.get("/payment-integrations/channels", response_model=list[ChannelResponse])
def channels(
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.AUDITOR)),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(PaymentChannel)
        .where(PaymentChannel.organization_id == context.organization_id)
        .order_by(PaymentChannel.created_at.desc())
        .limit(50)
    ).all()


@router.post("/payment-integrations/channels", response_model=ChannelResponse, status_code=201)
def connect(
    data: ChannelConnect,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    return connect_channel(db, context, data, request.state.correlation_id)


@router.post(
    "/payment-integrations/channels/{channel_id}/disconnect", response_model=ChannelResponse
)
def disconnect(
    channel_id: uuid.UUID,
    data: VerificationRevocation,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    lock_org(db, context.organization_id)
    fresh_mfa(context, data.totp_code)
    item = db.scalar(
        select(PaymentChannel).where(
            PaymentChannel.id == channel_id,
            PaymentChannel.organization_id == context.organization_id,
        )
    )
    if item is None:
        raise HTTPException(404, "Payment channel not found")
    item.status = "DISABLED"
    operation_audit(
        db, item, "DISCONNECT_PAYMENT_CHANNEL", context.user.id, request.state.correlation_id
    )
    db.commit()
    return item


@router.get("/collections", response_model=list[CollectionResponse])
def collections(context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)):
    return db.scalars(
        select(Collection)
        .where(Collection.organization_id == context.organization_id)
        .order_by(Collection.created_at.desc())
        .limit(200)
    ).all()


@router.post("/collections", response_model=CollectionResponse, status_code=201)
def create(
    data: CollectionCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    context: TenantContext = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    return create_receivable(db, context, data, idempotency_key, request.state.correlation_id)


@router.post("/collections/{collection_id}/reconcile", response_model=CollectionResponse)
def reconcile(
    collection_id: uuid.UUID,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    return reconcile_receivable(
        db, collection_id, context.organization_id, context.user.id, request.state.correlation_id
    )


@router.post("/payment-integrations/webhooks/payos/{channel_id}")
async def webhook(channel_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    item = db.get(PaymentChannel, channel_id)
    if item is None or item.purpose != "COLLECTION":
        raise HTTPException(404, "Payment channel not found")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 32 * 1024:
            raise HTTPException(413, "Webhook payload too large")
        body.extend(chunk)
    try:
        with gateway(item) as provider:
            data = provider.webhooks.verify(bytes(body))
    except Exception:
        raise HTTPException(401, "Invalid provider webhook signature") from None
    collection = db.scalar(
        select(Collection).where(
            Collection.channel_id == item.id, Collection.order_code == data.order_code
        )
    )
    if collection is None:
        return {
            "received": True,
            "ignored": True,
        }  # Signed registration sample never creates a receivable.
    # Only signed data is trusted. Redirect URL flags and unsigned envelope success are ignored.
    if data.code != "00" or data.currency != "VND" or data.account_number != account_of(item):
        raise HTTPException(409, "Provider receipt does not match the collection")
    if collection.payment_link_id and collection.payment_link_id != data.payment_link_id:
        raise HTTPException(409, "Provider receipt does not match the collection")
    # Never increment money from a callback. Fetch authenticated cumulative provider state instead.
    await run_in_threadpool(
        reconcile_receivable,
        db,
        collection.id,
        collection.organization_id,
        None,
        request.state.correlation_id,
    )
    return {"received": True, "ignored": False}
