import uuid

import pytest
from app.models.entities import PaymentRequest, PaymentStatus
from app.services.payments import transition
from fastapi import HTTPException


def payment(status: PaymentStatus) -> PaymentRequest:
    return PaymentRequest(organization_id=uuid.uuid4(), maker_id=uuid.uuid4(), status=status)


def test_allowed_lifecycle():
    value = payment(PaymentStatus.DRAFT)
    transition(value, PaymentStatus.PENDING_APPROVAL)
    transition(value, PaymentStatus.APPROVED)
    transition(value, PaymentStatus.SIGNED)
    assert value.status == PaymentStatus.SIGNED


def test_draft_cannot_jump_to_signed():
    with pytest.raises(HTTPException):
        transition(payment(PaymentStatus.DRAFT), PaymentStatus.SIGNED)
