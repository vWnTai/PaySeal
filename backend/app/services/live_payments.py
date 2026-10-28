import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext
from app.core.config import settings
from app.models.entities import (
    Collection,
    Organization,
    PaymentChannel,
    PaymentRequest,
    PaymentRequestVersion,
    Transfer,
)
from app.schemas.operations import ChannelConnect, CollectionCreate
from app.services.audit import add_audit_event
from app.services.business_verification import latest_verification, require_verified_business
from app.services.payments import _aware, _verify_recent_mfa
from app.services.payos_gateway import (
    account_of,
    create_collection,
    gateway,
    lookup_payout,
    payout_request,
    payout_state,
    require_live,
    validate_account,
    validate_collection,
)
from app.services.runtime import encryption_service
from app.services.verification import verify_payment


def lock_org(db: Session, organization_id: uuid.UUID) -> Organization:
    return db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def fresh_mfa(context: TenantContext, code: str | None) -> None:
    if not code:
        raise HTTPException(403, "MFA confirmation required")
    _verify_recent_mfa(context.user, code)


def require_live_signature(
    db: Session, organization: Organization, payment: PaymentRequest, verification: dict
) -> None:
    signed_issuer = verification.get("organization") or {}
    case = latest_verification(db, organization)
    if (
        signed_issuer.get("signed_verification_method") != "MANUAL_REVIEW"
        or (signed_issuer.get("name"), signed_issuer.get("tax_id"), signed_issuer.get("domain"))
        != (organization.name, organization.tax_id, organization.domain)
        or not case
        or not case.reviewed_at
        or not payment.signed_at
        or _aware(payment.signed_at) < _aware(case.reviewed_at)
    ):
        raise HTTPException(409, "Live transfers require a post-verification signature")


def active_channel(db: Session, organization_id: uuid.UUID, purpose: str) -> PaymentChannel:
    channel = db.scalar(
        select(PaymentChannel).where(
            PaymentChannel.organization_id == organization_id,
            PaymentChannel.purpose == purpose,
            PaymentChannel.status == "ACTIVE",
        )
    )
    if channel is None:
        raise HTTPException(409, "Payment channel is not connected")
    return channel


def operation_audit(
    db: Session, item, event: str, actor_id: uuid.UUID | None, correlation: str
) -> None:
    add_audit_event(
        db,
        organization_id=item.organization_id,
        actor_id=actor_id,
        event_type=event,
        object_type=item.__tablename__,
        object_id=str(item.id),
        data={"status": item.status},
        correlation_id=correlation,
    )


def connect_channel(
    db: Session, context: TenantContext, data: ChannelConnect, correlation: str
) -> PaymentChannel:
    require_live()
    organization = lock_org(db, context.organization_id)
    require_verified_business(db, organization)
    fresh_mfa(context, data.totp_code)
    if db.scalar(
        select(PaymentChannel.id).where(
            PaymentChannel.organization_id == organization.id,
            PaymentChannel.purpose == data.purpose,
            PaymentChannel.status.in_(["ACTIVE", "CONFIGURING"]),
        )
    ):
        raise HTTPException(409, "Disconnect the existing channel first")
    channel_id = uuid.uuid4()
    encrypted = encryption_service()
    item = PaymentChannel(
        id=channel_id,
        organization_id=organization.id,
        purpose=data.purpose,
        credentials_ciphertext=encrypted.encrypt(
            json.dumps(
                {
                    "client_id": data.client_id,
                    "api_key": data.api_key,
                    "checksum_key": data.checksum_key,
                }
            ),
            context=f"payos-credentials:{channel_id}".encode(),
        ),
        account_ciphertext=encrypted.encrypt(
            data.account_number, context=f"payos-account:{channel_id}".encode()
        ),
        account_last4=data.account_number[-4:],
        bank_bin=data.bank_bin,
        account_name=data.account_name,
        created_by=context.user.id,
        status="CONFIGURING",
    )
    db.add(item)
    operation_audit(db, item, "CONNECT_PAYMENT_CHANNEL_STARTED", context.user.id, correlation)
    db.commit()  # Webhook confirmation needs this binding visible before the outbound API call.
    succeeded = False
    try:
        with gateway(item) as provider:
            if item.purpose == "PAYOUT":
                result = provider.payouts_account.balance()
                if result.currency != "VND":
                    raise ValueError("Unsupported payout currency")
            else:
                callback = (
                    settings.public_app_url.rstrip("/")
                    + f"/api/v1/payment-integrations/webhooks/payos/{item.id}"
                )
                result = provider.webhooks.confirm(callback)
            validate_account(item, result.account_number, result.account_name)
            succeeded = True
    except Exception:
        # Never surface SDK exception text: it can contain credentials or bank account details.
        succeeded = False
    organization = lock_org(db, item.organization_id)
    db.refresh(item)
    if item.status != "CONFIGURING":
        raise HTTPException(409, "Payment channel configuration was interrupted")
    if succeeded:
        try:
            require_verified_business(db, organization)
        except HTTPException:
            succeeded = False
    item.status = "ACTIVE" if succeeded else "DISABLED"
    operation_audit(db, item, "CONNECT_PAYMENT_CHANNEL_FINISHED", context.user.id, correlation)
    db.commit()
    if not succeeded:
        raise HTTPException(502, "Payment channel could not be verified")
    return item


def create_receivable(
    db: Session, context: TenantContext, data: CollectionCreate, key: str, correlation: str
) -> Collection:
    require_live()
    organization = lock_org(db, context.organization_id)
    expires = _aware(data.expires_at)
    canonical = {
        "invoice_reference": data.invoice_reference,
        "amount_minor": data.amount_minor,
        "expires_at": expires.isoformat(),
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(
        select(Collection).where(
            Collection.organization_id == organization.id, Collection.idempotency_key == key
        )
    )
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(409, "Idempotency key was reused with a different request")
        return existing
    require_verified_business(db, organization)
    fresh_mfa(context, data.totp_code)
    now = datetime.now(timezone.utc)
    if not 60 <= (expires - now).total_seconds() <= 7 * 24 * 3600:
        raise HTTPException(422, "Collection expiry must be between one minute and seven days")
    channel = active_channel(db, organization.id, "COLLECTION")
    # 15-digit safe JS integer, cryptographically random; collision retry before contacting provider.
    order = secrets.randbelow(900_000_000_000_000) + 100_000_000_000_000
    while db.scalar(select(Collection.id).where(Collection.order_code == order)):
        order = secrets.randbelow(900_000_000_000_000) + 100_000_000_000_000
    item = Collection(
        id=uuid.uuid4(),
        organization_id=organization.id,
        channel_id=channel.id,
        created_by=context.user.id,
        idempotency_key=key,
        request_hash=fingerprint,
        invoice_reference=data.invoice_reference,
        amount_minor=data.amount_minor,
        order_code=order,
        expires_at=expires,
        status="DISPATCHING",
        amount_paid=0,
    )
    db.add(item)
    operation_audit(db, item, "CREATE_COLLECTION_STARTED", context.user.id, correlation)
    db.commit()  # Durable reservation. A retry returns this record, never another provider POST.
    result = None
    try:
        with gateway(channel) as provider:
            result = create_collection(provider, channel, item)
    except Exception:
        result = None
    lock_org(db, item.organization_id)
    db.refresh(item)
    if result:
        item.payment_link_id, item.checkout_url = result.payment_link_id, result.checkout_url
        if item.status == "DISPATCHING":
            item.status = "PENDING"  # A checkout creation response is never proof of receipt.
    elif item.status == "DISPATCHING":
        item.status = "UNKNOWN"
    operation_audit(db, item, "CREATE_COLLECTION_FINISHED", context.user.id, correlation)
    db.commit()
    return item


def reconcile_receivable(
    db: Session,
    collection_id: uuid.UUID,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    correlation: str,
) -> Collection:
    item = db.scalar(
        select(Collection).where(
            Collection.id == collection_id, Collection.organization_id == organization_id
        )
    )
    if item is None:
        raise HTTPException(404, "Collection not found")
    channel = db.get(PaymentChannel, item.channel_id)
    try:
        with gateway(channel) as provider:
            result = provider.payment_requests.get(item.order_code)
    except Exception:
        raise HTTPException(502, "Payment provider is temporarily unavailable") from None
    lock_org(db, organization_id)
    db.refresh(item)
    validate_collection(item, result)
    # Reconciliation works with old immutable credentials even if the channel is disconnected.
    expected_account = account_of(channel)
    if any(
        transaction.account_number != expected_account or transaction.amount <= 0
        for transaction in result.transactions
    ):
        raise HTTPException(409, "Provider receipt does not match the collection")
    references = [transaction.reference for transaction in result.transactions]
    if (
        len(set(references)) != len(references)
        or sum(transaction.amount for transaction in result.transactions) != result.amount_paid
    ):
        raise HTTPException(409, "Provider receipt does not match the collection")
    if item.status == "PAID" and result.status != "PAID":
        raise HTTPException(409, "Terminal collection outcome cannot be changed")
    item.amount_paid, item.status, item.payment_link_id = (
        result.amount_paid,
        result.status,
        result.id,
    )
    item.reconciled_at = datetime.now(timezone.utc)
    item.reconciliation_attempted_at = item.reconciled_at
    operation_audit(db, item, "RECONCILE_COLLECTION", actor_id, correlation)
    db.commit()
    return item


def signed_transfer_payload(db: Session, item: Transfer) -> dict:
    version = db.scalar(
        select(PaymentRequestVersion).where(
            PaymentRequestVersion.payment_request_id == item.payment_request_id,
            PaymentRequestVersion.version == item.payment_version,
        )
    )
    return version.payload_json


def apply_live_result(item: Transfer, state: str) -> None:
    if item.status in {"SUCCEEDED", "FAILED", "REVERSED"} and state != item.status:
        # A reversal is not a failure and may legitimately arrive after success.
        if not (item.status == "SUCCEEDED" and state == "REVERSED"):
            raise HTTPException(409, "Terminal transfer outcome cannot be changed")
    item.status = state
    item.failure_reason = (
        "Provider reported failure; do not resubmit automatically" if state == "FAILED" else None
    )
    if state in {"SUCCEEDED", "FAILED", "REVERSED"}:
        item.completed_at = item.completed_at or datetime.now(timezone.utc)


def dispatch_transfer(
    db: Session,
    transfer_id: uuid.UUID,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    correlation: str,
) -> Transfer:
    require_live()
    organization = lock_org(db, organization_id)
    item = db.scalar(
        select(Transfer)
        .where(Transfer.id == transfer_id, Transfer.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise HTTPException(404, "Transfer not found")
    if item.provider != "payos" or item.status != "QUEUED":
        return item  # DISPATCHING/UNKNOWN can only be queried, never submitted again.
    require_verified_business(db, organization)
    channel = db.get(PaymentChannel, item.channel_id)
    payment = db.get(PaymentRequest, item.payment_request_id)
    payload = signed_transfer_payload(db, item)
    verification = verify_payment(db, payment)
    require_live_signature(db, organization, payment, verification)
    if (
        channel.status != "ACTIVE"
        or channel.organization_id != item.organization_id
        or channel.purpose != "PAYOUT"
        or payment.status.value != "SIGNED"
        or payment.current_version != item.payment_version
        or verification["status"] != "VERIFIED"
        or item.amount_minor != payload["payment"]["amount_minor"]
        or item.currency != payload["payment"]["currency"]
        or item.bank_code != payload["beneficiary"]["bank_code"]
        or item.account_last4 != payload["beneficiary"]["account_number"][-4:]
        or item.beneficiary_name != payload["beneficiary"]["name"]
        or item.invoice_reference != payload["invoice"]["reference"]
        or item.amount_minor > settings.max_live_transfer_amount
        or _aware(datetime.fromisoformat(payload["expires_at"])) <= datetime.now(timezone.utc)
    ):
        item.status = "FAILED"
        item.failure_reason = "Pre-dispatch safety check failed; no provider request sent"
        operation_audit(db, item, "LIVE_TRANSFER_BLOCKED", actor_id, correlation)
        db.commit()
        return item
    item.status, item.dispatched_at = "DISPATCHING", datetime.now(timezone.utc)
    operation_audit(db, item, "LIVE_TRANSFER_DISPATCH_STARTED", actor_id, correlation)
    db.commit()  # Commit before the financial side effect, never after sending for the first time.
    state = "UNKNOWN"
    try:
        with gateway(channel) as provider:
            source = provider.payouts_account.balance()
            validate_account(channel, source.account_number, source.account_name)
            if source.currency != "VND":
                raise ValueError("Unsupported source currency")
            result = provider.payouts.create(
                payout_request(item, payload), idempotency_key=str(item.id)
            )
            state = payout_state(item, payload, result)
    except Exception:
        state = "UNKNOWN"
    lock_org(db, organization_id)
    db.refresh(item)
    if item.status == "DISPATCHING":
        apply_live_result(item, state)
    operation_audit(db, item, "LIVE_TRANSFER_DISPATCH_FINISHED", actor_id, correlation)
    db.commit()
    return item


def reconcile_live_transfer(
    db: Session, item: Transfer, actor_id: uuid.UUID | None, correlation: str
) -> Transfer:
    channel = db.get(PaymentChannel, item.channel_id)
    payload = signed_transfer_payload(db, item)
    try:
        with gateway(channel) as provider:
            result = lookup_payout(provider, item)
            state = payout_state(item, payload, result)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Payment provider is temporarily unavailable") from None
    lock_org(db, item.organization_id)
    db.refresh(item)
    apply_live_result(item, state)
    item.reconciled_at = datetime.now(timezone.utc)
    item.reconciliation_attempted_at = item.reconciled_at
    operation_audit(db, item, "RECONCILE_LIVE_TRANSFER", actor_id, correlation)
    db.commit()
    return item
