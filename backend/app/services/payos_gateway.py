"""Official SDK boundary: fixed HTTPS endpoint, authenticated responses, no blind retries."""

import base64
import ipaddress
import json
from urllib.parse import urlsplit

from fastapi import HTTPException
from payos import PayOS
from payos.types import CreatePaymentLinkRequest, GetPayoutListParams, PayoutRequest

from app.core.config import settings
from app.models.entities import Collection, PaymentChannel, Transfer
from app.services.runtime import encryption_service


def live_blockers() -> list[str]:
    issues = []
    if not settings.payments_live_enabled:
        issues.append("LIVE_DISABLED")
    if settings.environment != "production":
        issues.append("PRODUCTION_REQUIRED")
    url = urlsplit(settings.public_app_url)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or (url.hostname or "").endswith((".local", ".localhost", ".internal", ".test", ".invalid"))
        or "." not in (url.hostname or "")
    ):
        issues.append("HTTPS_DOMAIN_REQUIRED")
    if not settings.refresh_cookie_secure:
        issues.append("SECURE_COOKIE_REQUIRED")
    if not settings.account_encryption_key:
        issues.append("ENCRYPTION_KEY_REQUIRED")
    else:
        try:
            key = base64.urlsafe_b64decode(
                settings.account_encryption_key + "=" * (-len(settings.account_encryption_key) % 4)
            )
            if len(key) != 32 or key == b"\x00" * 32:
                issues.append("ENCRYPTION_KEY_REQUIRED")
        except Exception:
            issues.append("ENCRYPTION_KEY_REQUIRED")
    try:
        ipaddress.ip_address(url.hostname or "")
        if "HTTPS_DOMAIN_REQUIRED" not in issues:
            issues.append("HTTPS_DOMAIN_REQUIRED")
    except ValueError:
        pass
    if (
        url.hostname not in settings.trusted_host_list
        or settings.public_app_url.rstrip("/") not in settings.cors_origin_list
    ):
        issues.append("ORIGIN_HOST_REQUIRED")
    if not settings.database_url.startswith("postgresql"):
        issues.append("POSTGRES_REQUIRED")
    secrets = (
        settings.jwt_secret,
        settings.refresh_token_secret,
        settings.account_lookup_hmac_key,
        settings.key_encryption_secret,
        settings.minio_secret_key,
    )
    if any("dev" in secret.lower() or len(secret) < 32 for secret in secrets):
        issues.append("PRODUCTION_SECRETS_REQUIRED")
    if settings.max_live_transfer_amount <= 0:
        issues.append("TRANSFER_LIMIT_REQUIRED")
    return issues


def require_live() -> None:
    if live_blockers():
        raise HTTPException(503, "Live payments are not ready")


def account_of(channel: PaymentChannel) -> str:
    return encryption_service().decrypt(
        channel.account_ciphertext, context=f"payos-account:{channel.id}".encode()
    )


def gateway(channel: PaymentChannel) -> PayOS:
    credentials = json.loads(
        encryption_service().decrypt(
            channel.credentials_ciphertext, context=f"payos-credentials:{channel.id}".encode()
        )
    )
    return PayOS(**credentials, base_url="https://api-merchant.payos.vn", timeout=15, max_retries=0)


def validate_account(channel: PaymentChannel, account_number: str, account_name: str) -> None:
    # Exact account binding; name must match the provider's canonical display name too.
    if account_number != account_of(channel) or " ".join(account_name.upper().split()) != " ".join(
        channel.account_name.upper().split()
    ):
        raise HTTPException(409, "Provider account does not match the channel")


def create_collection(client: PayOS, channel: PaymentChannel, item: Collection):
    destination = settings.public_app_url.rstrip("/") + "/collections"
    result = client.payment_requests.create(
        CreatePaymentLinkRequest(
            order_code=item.order_code,
            amount=item.amount_minor,
            description=str(item.order_code)[-9:],
            cancel_url=destination,
            return_url=destination,
            expired_at=int(item.expires_at.timestamp()),
        )
    )
    validate_account(channel, result.account_number, result.account_name)
    url = urlsplit(result.checkout_url)
    if (
        result.order_code != item.order_code
        or result.amount != item.amount_minor
        or result.currency != "VND"
        or result.bin != channel.bank_bin
        or url.scheme != "https"
        or url.hostname != "pay.payos.vn"
        or url.username
        or url.port not in {None, 443}
    ):
        raise HTTPException(409, "Provider receipt does not match the collection")
    return result


def validate_collection(item: Collection, result) -> None:
    if (
        result.order_code != item.order_code
        or result.amount != item.amount_minor
        or (item.payment_link_id and result.id != item.payment_link_id)
    ):
        raise HTTPException(409, "Provider receipt does not match the collection")
    if result.amount_paid < item.amount_paid or result.amount_paid < 0:
        raise HTTPException(409, "Provider receipt does not match the collection")
    if result.status == "PAID" and result.amount_paid < item.amount_minor:
        raise HTTPException(409, "Provider receipt does not match the collection")


def payout_request(item: Transfer, payload: dict) -> PayoutRequest:
    return PayoutRequest(
        reference_id=item.provider_reference,
        amount=payload["payment"]["amount_minor"],
        description="PS " + item.id.hex[:12],
        to_bin=payload["beneficiary"]["bank_code"],
        to_account_number=payload["beneficiary"]["account_number"],
    )


def lookup_payout(client: PayOS, item: Transfer):
    page = client.payouts.list(GetPayoutListParams(reference_id=item.provider_reference, limit=2))
    matches = page.data
    if len(matches) != 1:
        raise HTTPException(409, "Payout outcome is still unknown")
    return matches[0]


def payout_state(item: Transfer, payload: dict, result) -> str:
    if result.reference_id != item.provider_reference or len(result.transactions) != 1:
        raise HTTPException(409, "Provider receipt does not match the transfer")
    transaction = result.transactions[0]
    if (
        item.amount_minor != payload["payment"]["amount_minor"]
        or item.currency != payload["payment"]["currency"]
        or item.bank_code != payload["beneficiary"]["bank_code"]
        or item.account_last4 != payload["beneficiary"]["account_number"][-4:]
        or transaction.reference_id != item.provider_reference
        or transaction.amount != item.amount_minor
        or transaction.to_bin != payload["beneficiary"]["bank_code"]
        or transaction.to_account_number != payload["beneficiary"]["account_number"]
    ):
        raise HTTPException(409, "Provider receipt does not match the transfer")
    return {
        "SUCCEEDED": "SUCCEEDED",
        "FAILED": "FAILED",
        "CANCELLED": "FAILED",
        "REVERSED": "REVERSED",
        "ON_HOLD": "ON_HOLD",
    }.get(transaction.state, "SUBMITTED")
