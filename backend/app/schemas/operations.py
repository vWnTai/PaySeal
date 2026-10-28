import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VerificationDecision(StrictRequest):
    decision: Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]
    reason: str = Field(min_length=20, max_length=1000)
    registration_checked: bool = False
    tax_checked: bool = False
    authority_checked: bool = False
    totp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class VerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    profile: dict[str, str]
    representative_name: str
    contact_email: str
    registered_address: str
    registration_number: str
    document_sha256: str
    status: str
    review_reason: str | None
    review_checks: dict[str, bool] | None
    reviewed_at: datetime | None
    valid_until: datetime | None
    created_at: datetime


class VerificationRevocation(StrictRequest):
    reason: str = Field(min_length=20, max_length=1000)
    totp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class TransferCreate(StrictRequest):
    payment_request_id: uuid.UUID
    totp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    confirm_live: bool = False


class TransferDispatch(StrictRequest):
    confirm_live: Literal[True]
    totp_code: str = Field(pattern=r"^[0-9]{6}$", repr=False)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    payment_request_id: uuid.UUID
    payment_version: int
    provider: str
    provider_reference: str
    status: str
    amount_minor: int
    currency: str
    beneficiary_name: str
    bank_code: str
    account_last4: str
    invoice_reference: str
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None
    reconciled_at: datetime | None


class SandboxOutcome(StrictRequest):
    status: Literal["SUCCEEDED", "FAILED"]
    deliver_event: bool = True


class TransferWebhook(StrictRequest):
    event_id: uuid.UUID
    provider_reference: str = Field(min_length=1, max_length=100)
    status: Literal["SUCCEEDED", "FAILED"]
    amount_minor: int = Field(gt=0)
    currency: Literal["VND"]


class ChannelConnect(StrictRequest):
    purpose: Literal["COLLECTION", "PAYOUT"]
    client_id: str = Field(min_length=8, max_length=200, repr=False)
    api_key: str = Field(min_length=16, max_length=300, repr=False)
    checksum_key: str = Field(min_length=16, max_length=300, repr=False)
    bank_bin: str = Field(pattern=r"^[0-9]{6}$")
    account_number: str = Field(min_length=4, max_length=34, pattern=r"^[0-9]+$", repr=False)
    account_name: str = Field(min_length=2, max_length=200)
    attested: Literal[True]
    totp_code: str = Field(pattern=r"^[0-9]{6}$", repr=False)


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    purpose: str
    status: str
    bank_bin: str
    account_last4: str
    account_name: str
    created_at: datetime


class CollectionCreate(StrictRequest):
    invoice_reference: str = Field(min_length=1, max_length=160)
    amount_minor: int = Field(gt=0, le=2_000_000_000)
    expires_at: datetime
    totp_code: str = Field(pattern=r"^[0-9]{6}$", repr=False)


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    invoice_reference: str
    order_code: int
    amount_minor: int
    amount_paid: int
    status: str
    checkout_url: str | None
    expires_at: datetime
    reconciled_at: datetime | None
    created_at: datetime
