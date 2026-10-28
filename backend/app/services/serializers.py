from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Approval, Beneficiary, PaymentRequest
from app.services.payments import current_version


def beneficiary_dict(value: Beneficiary) -> dict:
    return {
        "id": value.id,
        "organization_id": value.organization_id,
        "name": value.name,
        "bank_code": value.bank_code,
        "account_masked": "*" * 6 + value.account_last4,
        "status": value.status.value,
        "verified_at": value.verified_at,
        "created_at": value.created_at,
    }


def payment_dict(db: Session, value: PaymentRequest) -> dict:
    version = current_version(db, value)
    approvals = (
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.payment_request_id == value.id, Approval.decision == "APPROVED")
        )
        or 0
    )
    return {
        "id": value.id,
        "organization_id": value.organization_id,
        "status": value.status.value,
        "current_version": value.current_version,
        "invoice_reference": version.invoice_reference,
        "currency": version.currency,
        "amount_minor": version.amount_minor,
        "beneficiary_id": version.beneficiary_id,
        "beneficiary_name": version.beneficiary_name,
        "bank_code": version.bank_code,
        "account_masked": "*" * 6 + version.account_last4,
        "expires_at": version.expires_at,
        "created_at": value.created_at,
        "approvals_required": value.approvals_required,
        "approvals_completed": approvals,
        "recent_mfa_required": value.recent_mfa_required,
        "public_url": f"{settings.public_verify_base_url.rstrip('/')}/{value.public_token}"
        if value.public_token
        else None,
    }
