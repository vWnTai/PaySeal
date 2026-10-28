from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
Email = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=320,
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    ),
]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    full_name: Annotated[
        str, StringConstraints(min_length=2, max_length=160, strip_whitespace=True)
    ]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    csrf_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: Email
    full_name: str
    mfa_enabled: bool
    is_platform_reviewer: bool = False
    organizations: list[dict[str, Any]] = []


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    tax_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    domain: str = Field(min_length=3, max_length=253)


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    domain: str | None = Field(default=None, min_length=3, max_length=253)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    tax_id: str
    domain: str
    verification_level: int
    verification_status: str = "UNVERIFIED"
    verification_method: str | None = None
    verification_valid_until: datetime | None = None
    status: str
    created_at: datetime


class MemberCreate(BaseModel):
    email: Email
    role: str


class MemberPatch(BaseModel):
    role: str


class BeneficiaryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    bank_code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    account_number: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class BeneficiaryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    bank_code: str | None = Field(
        default=None, min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$"
    )
    status: str | None = None


class AccountChangeRequest(BaseModel):
    account_number: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class BeneficiaryResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    bank_code: str
    account_masked: str
    status: str
    verified_at: datetime | None
    created_at: datetime


class PaymentCreate(BaseModel):
    invoice_reference: str = Field(min_length=1, max_length=160)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    amount_minor: int = Field(gt=0, le=9_000_000_000_000_000)
    beneficiary_id: uuid.UUID
    expires_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.upper()


class PaymentPatch(BaseModel):
    invoice_reference: str | None = Field(default=None, min_length=1, max_length=160)
    amount_minor: int | None = Field(default=None, gt=0)
    beneficiary_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)
    totp_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    status: str
    current_version: int
    invoice_reference: str
    currency: str
    amount_minor: int
    beneficiary_id: uuid.UUID
    beneficiary_name: str
    bank_code: str
    account_masked: str
    expires_at: datetime
    created_at: datetime
    approvals_required: int
    approvals_completed: int
    recent_mfa_required: bool
    public_url: str | None = None


class MfaCode(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class PublicVerificationResponse(BaseModel):
    status: str
    signature_valid: bool
    issuer_verified: bool
    document_status: str
    expired: bool
    revoked: bool
    superseded: bool
    organization: dict[str, Any] | None
    payment: dict[str, Any] | None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    warnings: list[str] = []
