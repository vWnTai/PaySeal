from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, require_roles, tenant_context
from app.core.database import get_db
from app.models.entities import (
    Beneficiary,
    BeneficiaryChangeRequest,
    BeneficiaryStatus,
    Role,
)
from app.schemas.api import (
    AccountChangeRequest,
    BeneficiaryCreate,
    BeneficiaryPatch,
    BeneficiaryResponse,
)
from app.services.audit import add_audit_event
from app.services.runtime import encryption_service
from app.services.serializers import beneficiary_dict

router = APIRouter(prefix="/beneficiaries", tags=["Beneficiaries"])


@router.post("", response_model=BeneficiaryResponse, status_code=201)
def create_beneficiary(
    data: BeneficiaryCreate,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    crypto = encryption_service()
    value = Beneficiary(
        organization_id=context.organization_id,
        name=data.name,
        bank_code=data.bank_code.upper(),
        account_ciphertext=crypto.encrypt(data.account_number),
        account_lookup_hash=crypto.lookup_hash(data.account_number),
        account_last4=data.account_number[-4:],
    )
    db.add(value)
    db.flush()
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="CREATE_BENEFICIARY",
        object_type="beneficiary",
        object_id=str(value.id),
        data={
            "name": value.name,
            "bank_code": value.bank_code,
            "account_masked": crypto.mask(data.account_number),
        },
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return beneficiary_dict(value)


@router.get("", response_model=list[BeneficiaryResponse])
def list_beneficiaries(
    context: TenantContext = Depends(tenant_context), db: Session = Depends(get_db)
):
    values = db.scalars(
        select(Beneficiary)
        .where(Beneficiary.organization_id == context.organization_id)
        .order_by(Beneficiary.created_at.desc())
    ).all()
    return [beneficiary_dict(item) for item in values]


def _get(db: Session, organization_id: uuid.UUID, beneficiary_id: uuid.UUID) -> Beneficiary:
    value = db.scalar(
        select(Beneficiary).where(
            Beneficiary.id == beneficiary_id,
            Beneficiary.organization_id == organization_id,
        )
    )
    if value is None:
        raise HTTPException(404, "Beneficiary not found")
    return value


@router.get("/{beneficiary_id}", response_model=BeneficiaryResponse)
def get_beneficiary(
    beneficiary_id: uuid.UUID,
    context: TenantContext = Depends(tenant_context),
    db: Session = Depends(get_db),
):
    return beneficiary_dict(_get(db, context.organization_id, beneficiary_id))


@router.patch("/{beneficiary_id}", response_model=BeneficiaryResponse)
def patch_beneficiary(
    beneficiary_id: uuid.UUID,
    data: BeneficiaryPatch,
    request: Request,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    value = _get(db, context.organization_id, beneficiary_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes:
        try:
            changes["status"] = BeneficiaryStatus(changes["status"])
        except ValueError as exc:
            raise HTTPException(422, "Invalid beneficiary status") from exc
    for key, item in changes.items():
        setattr(value, key, item.upper() if key == "bank_code" else item)
    add_audit_event(
        db,
        organization_id=context.organization_id,
        actor_id=context.user.id,
        event_type="UPDATE_BENEFICIARY",
        object_type="beneficiary",
        object_id=str(value.id),
        data={"fields": list(changes)},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return beneficiary_dict(value)


@router.post("/{beneficiary_id}/change-request", status_code=201)
def request_account_change(
    beneficiary_id: uuid.UUID,
    data: AccountChangeRequest,
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.MAKER)),
    db: Session = Depends(get_db),
):
    value = db.scalar(
        select(Beneficiary)
        .where(
            Beneficiary.id == beneficiary_id,
            Beneficiary.organization_id == context.organization_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, "Beneficiary not found")
    crypto = encryption_service()
    change = BeneficiaryChangeRequest(
        beneficiary_id=value.id,
        organization_id=context.organization_id,
        account_ciphertext=crypto.encrypt(data.account_number),
        account_lookup_hash=crypto.lookup_hash(data.account_number),
        account_last4=data.account_number[-4:],
        created_by=context.user.id,
    )
    db.add(change)
    db.commit()
    return {
        "id": change.id,
        "status": change.status,
        "account_masked": crypto.mask(data.account_number),
    }
