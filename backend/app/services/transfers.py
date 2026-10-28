import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext
from app.core.config import settings
from app.models.entities import PaymentRequest, Transfer
from app.services.business_verification import require_verified_business
from app.services.live_payments import active_channel, fresh_mfa, lock_org, require_live_signature
from app.services.payments import _aware, _verify_recent_mfa, current_version
from app.services.payos_gateway import require_live
from app.services.transfer_provider import ProviderReceipt, TransferInstruction, transfer_provider
from app.services.verification import verify_payment


def create_transfer(
    db: Session,
    context: TenantContext,
    payment_id: uuid.UUID,
    key: str,
    code: str | None,
    confirm_live: bool = False,
) -> tuple[Transfer, bool]:
    live = settings.transfer_mode == "live"
    if live:
        require_live()
        provider = None
    else:
        provider = transfer_provider(db)
    organization = lock_org(db, context.organization_id)
    existing = db.scalar(
        select(Transfer).where(
            Transfer.organization_id == context.organization_id, Transfer.idempotency_key == key
        )
    )
    if existing:
        if existing.payment_request_id != payment_id:
            raise HTTPException(409, "Idempotency key was reused with a different request")
        return existing, False
    payment = db.scalar(
        select(PaymentRequest)
        .where(
            PaymentRequest.id == payment_id,
            PaymentRequest.organization_id == context.organization_id,
        )
        .with_for_update()
    )
    if payment is None:
        raise HTTPException(404, "Payment request not found")
    if payment.maker_id == context.user.id:
        raise HTTPException(403, "Maker cannot initiate their own transfer")
    require_verified_business(db, organization)
    verification = verify_payment(db, payment)
    if payment.status.value != "SIGNED" or verification["status"] != "VERIFIED":
        raise HTTPException(409, "Only active verified signed payments can be transferred")
    version = current_version(db, payment)
    payload = version.payload_json
    if _aware(datetime.fromisoformat(payload["expires_at"])) <= datetime.now(timezone.utc):
        raise HTTPException(409, "Signed payment has expired")
    if payload["payment"]["currency"] != "VND":
        raise HTTPException(422, "Sandbox transfers support VND only")
    _verify_recent_mfa(context.user, code)
    existing = db.scalar(
        select(Transfer).where(
            Transfer.payment_request_id == payment.id, Transfer.payment_version == version.version
        )
    )
    if existing:
        return existing, False  # Even a new idempotency key cannot transfer the same version twice.
    channel = None
    if live:
        require_live_signature(db, organization, payment, verification)
        if not confirm_live:
            raise HTTPException(409, "Explicit real money confirmation required")
        fresh_mfa(context, code)
        if payload["payment"]["amount_minor"] > settings.max_live_transfer_amount:
            raise HTTPException(409, "Live transfer exceeds the configured safety limit")
        if not re.fullmatch(r"[0-9]{6}", payload["beneficiary"]["bank_code"]):
            raise HTTPException(422, "Live transfers require a six digit bank BIN")
        if not re.fullmatch(r"[0-9]{4,34}", payload["beneficiary"]["account_number"]):
            raise HTTPException(422, "Live transfers require a numeric account number")
        channel = active_channel(db, context.organization_id, "PAYOUT")
    transfer_id = uuid.uuid4()
    receipt = (
        ProviderReceipt(
            f"ps_{transfer_id.hex}", "PENDING", payload["payment"]["amount_minor"], "VND"
        )
        if live
        else provider.submit(
            TransferInstruction(
                transfer_id,
                payload["payment"]["amount_minor"],
                payload["payment"]["currency"],
                payload["beneficiary"]["bank_code"],
                payload["beneficiary"]["account_number"],
            )
        )
    )
    item = Transfer(
        id=transfer_id,
        organization_id=context.organization_id,
        payment_request_id=payment.id,
        payment_version=version.version,
        created_by=context.user.id,
        idempotency_key=key,
        provider="payos" if live else "sandbox",
        provider_reference=receipt.reference,
        status="QUEUED" if live else "SUBMITTED",
        channel_id=channel.id if channel else None,
        amount_minor=receipt.amount_minor,
        currency=receipt.currency,
        beneficiary_name=payload["beneficiary"]["name"],
        bank_code=payload["beneficiary"]["bank_code"],
        account_last4=payload["beneficiary"]["account_number"][-4:],
        invoice_reference=payload["invoice"]["reference"],
    )
    db.add(item)
    db.flush()
    return item, True


def apply_receipt(item: Transfer, receipt: ProviderReceipt) -> bool:
    if (
        item.provider_reference != receipt.reference
        or item.amount_minor != receipt.amount_minor
        or item.currency != receipt.currency
    ):
        raise HTTPException(409, "Provider receipt does not match the transfer")
    if receipt.status == "PENDING":
        return False
    if receipt.status not in {"SUCCEEDED", "FAILED"}:
        raise HTTPException(422, "Invalid provider outcome")
    if item.status in {"SUCCEEDED", "FAILED"}:
        if item.status != receipt.status:
            raise HTTPException(409, "Terminal transfer outcome cannot be changed")
        return False
    item.status = receipt.status
    item.completed_at = datetime.now(timezone.utc)
    item.failure_reason = (
        "Sandbox provider simulated a failed transfer" if receipt.status == "FAILED" else None
    )
    return True
