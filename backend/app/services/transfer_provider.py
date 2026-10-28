import uuid
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import SandboxReceipt


@dataclass(frozen=True)
class TransferInstruction:
    transfer_id: uuid.UUID
    amount_minor: int
    currency: str
    bank_code: str
    account_number: str = field(repr=False)


@dataclass(frozen=True)
class ProviderReceipt:
    reference: str
    status: str
    amount_minor: int
    currency: str


class TransferProvider(Protocol):
    def submit(self, instruction: TransferInstruction) -> ProviderReceipt: ...
    def lookup(self, reference: str) -> ProviderReceipt: ...


class SandboxTransferProvider:
    """DB-backed sandbox, no network calls, bank access or real money movement."""

    def __init__(self, db: Session):
        self.db = db

    def submit(self, instruction: TransferInstruction) -> ProviderReceipt:
        reference = f"sandbox_{instruction.transfer_id.hex}"
        record = self.db.get(SandboxReceipt, reference)
        if record is None:
            record = SandboxReceipt(
                provider_reference=reference,
                amount_minor=instruction.amount_minor,
                currency=instruction.currency,
                status="PENDING",
            )
            self.db.add(record)
            self.db.flush()
        return ProviderReceipt(reference, record.status, record.amount_minor, record.currency)

    def lookup(self, reference: str) -> ProviderReceipt:
        record = self.db.get(SandboxReceipt, reference)
        if record is None:
            raise HTTPException(409, "Provider receipt not found")
        return ProviderReceipt(reference, record.status, record.amount_minor, record.currency)


def transfer_provider(db: Session) -> TransferProvider:
    if settings.transfer_mode != "sandbox":
        raise HTTPException(
            503,
            "Live transfers are not configured"
            if settings.transfer_mode == "live"
            else "Transfers are disabled",
        )
    return SandboxTransferProvider(db)
