import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_platform_reviewer
from app.api.organizations import _membership
from app.core.config import settings
from app.core.database import get_db
from app.crypto.canonical import sha256_hex
from app.models.entities import BusinessVerification, Membership, Organization, Role, User
from app.schemas.api import Email
from app.schemas.operations import (
    VerificationDecision,
    VerificationResponse,
    VerificationRevocation,
)
from app.services.audit import add_audit_event
from app.services.business_verification import (
    approve_verification,
    latest_verification,
    profile_of,
    retire_active_certificates,
    verification_state,
)
from app.services.documents import MinioStorage
from app.services.payments import _verify_recent_mfa

router = APIRouter(tags=["Business verification"])


def storage() -> MinioStorage:
    return MinioStorage()


def audit(
    db: Session, request: Request, user: User, item: BusinessVerification, event: str
) -> None:
    add_audit_event(
        db,
        organization_id=item.organization_id,
        actor_id=user.id,
        event_type=event,
        object_type="business_verification",
        object_id=str(item.id),
        data={"status": item.status, "document_sha256": item.document_sha256},
        correlation_id=request.state.correlation_id,
    )


@router.get(
    "/organizations/{organization_id}/verification", response_model=list[VerificationResponse]
)
def history(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(db, organization_id, user.id, {Role.OWNER, Role.AUDITOR})
    return db.scalars(
        select(BusinessVerification)
        .where(BusinessVerification.organization_id == organization_id)
        .order_by(BusinessVerification.created_at.desc())
        .limit(50)
    ).all()


@router.post(
    "/organizations/{organization_id}/verification",
    response_model=VerificationResponse,
    status_code=201,
)
def submit(
    organization_id: uuid.UUID,
    request: Request,
    document: UploadFile,
    registration_number: Annotated[str, Form(min_length=3, max_length=100)],
    representative_name: Annotated[str, Form(min_length=2, max_length=160)],
    registered_address: Annotated[str, Form(min_length=5, max_length=500)],
    contact_email: Annotated[Email, Form()],
    attested: Annotated[bool, Form()],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    document_storage: MinioStorage = Depends(storage),
):
    _membership(db, organization_id, user.id, {Role.OWNER})
    organization = db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None:
        raise HTTPException(404, "Organization not found")
    if not attested or not all(
        value.strip() for value in (registration_number, representative_name, registered_address)
    ):
        raise HTTPException(422, "Business information and attestation required")
    previous = latest_verification(db, organization)
    if previous and previous.status == "PENDING":
        raise HTTPException(409, "Verification is already pending")
    # A verified business can resubmit only after expiry or identity changes.
    if previous and previous.status == "APPROVED":
        if verification_state(db, organization)["verification_status"] == "APPROVED":
            raise HTTPException(409, "Business is already verified")
    data = document.file.read(settings.max_business_document_bytes + 1)
    if len(data) > settings.max_business_document_bytes:
        raise HTTPException(413, "Business document is too large")
    if document.content_type != "application/pdf" or not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Business document must be a PDF")
    object_key = f"business-verification/{uuid.uuid4()}.pdf"
    document_storage.put_pdf(object_key, data)
    item = BusinessVerification(
        organization_id=organization_id,
        submitted_by=user.id,
        profile=profile_of(organization),
        registration_number=registration_number.strip(),
        representative_name=representative_name.strip(),
        registered_address=registered_address.strip(),
        contact_email=contact_email,
        document_object_key=object_key,
        document_sha256=sha256_hex(data),
    )
    db.add(item)
    db.flush()
    audit(db, request, user, item, "SUBMIT_BUSINESS_VERIFICATION")
    db.commit()
    return item


@router.get("/platform/verifications", response_model=list[VerificationResponse])
def queue(
    user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db),
    offset: int = 0,
    status: str = "PENDING",
):
    if offset < 0:
        raise HTTPException(422, "Invalid offset")
    if status not in {"PENDING", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "REVOKED", "STALE"}:
        raise HTTPException(422, "Invalid verification status")
    # Reviewers must never handle a company they belong to.
    own_orgs = select(Membership.organization_id).where(Membership.user_id == user.id)
    return db.scalars(
        select(BusinessVerification)
        .where(
            BusinessVerification.status == status,
            BusinessVerification.organization_id.not_in(own_orgs),
            BusinessVerification.submitted_by != user.id,
        )
        .order_by(BusinessVerification.created_at)
        .offset(offset)
        .limit(50)
    ).all()


def independent_reviewer(db: Session, user: User, item: BusinessVerification) -> None:
    if item.submitted_by == user.id or db.scalar(
        select(Membership.id).where(
            Membership.organization_id == item.organization_id, Membership.user_id == user.id
        )
    ):
        raise HTTPException(403, "Reviewer cannot review their own organization")


@router.get("/platform/verifications/{submission_id}/document")
def download(
    submission_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db),
    document_storage: MinioStorage = Depends(storage),
):
    item = db.get(BusinessVerification, submission_id)
    if item is None:
        raise HTTPException(404, "Verification not found")
    independent_reviewer(db, user, item)
    data = document_storage.get_pdf(item.document_object_key)
    if sha256_hex(data) != item.document_sha256:
        raise HTTPException(409, "Business document integrity mismatch")
    audit(db, request, user, item, "DOWNLOAD_BUSINESS_DOCUMENT")
    db.commit()
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="business-{item.id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/platform/verifications/{submission_id}/review", response_model=VerificationResponse)
def review(
    submission_id: uuid.UUID,
    data: VerificationDecision,
    request: Request,
    user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db),
):
    item = db.get(BusinessVerification, submission_id)
    if item is None:
        raise HTTPException(404, "Verification not found")
    # All verification/profile mutations lock organization first, then the submission.
    organization = db.scalar(
        select(Organization).where(Organization.id == item.organization_id).with_for_update()
    )
    item = db.scalar(
        select(BusinessVerification)
        .where(BusinessVerification.id == submission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    independent_reviewer(db, user, item)
    if item.status != "PENDING":
        raise HTTPException(409, "Verification has already been reviewed")
    if item.profile != profile_of(organization):
        raise HTTPException(409, "Organization identity has changed")
    _verify_recent_mfa(user, data.totp_code)
    checks = {
        "registration_checked": data.registration_checked,
        "tax_checked": data.tax_checked,
        "authority_checked": data.authority_checked,
    }
    if data.decision == "APPROVED" and not all(checks.values()):
        raise HTTPException(422, "All verification checks are required")
    item.status, item.review_reason, item.review_checks = data.decision, data.reason, checks
    item.reviewed_by, item.reviewed_at = user.id, datetime.now(timezone.utc)
    if data.decision == "APPROVED":
        approve_verification(db, organization, item)
    else:
        organization.verification_level = 0
    audit(db, request, user, item, "REVIEW_BUSINESS_VERIFICATION")
    db.commit()
    return item


@router.post("/platform/verifications/{submission_id}/revoke", response_model=VerificationResponse)
def revoke(
    submission_id: uuid.UUID,
    data: VerificationRevocation,
    request: Request,
    user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db),
):
    item = db.get(BusinessVerification, submission_id)
    if item is None:
        raise HTTPException(404, "Verification not found")
    organization = db.scalar(
        select(Organization).where(Organization.id == item.organization_id).with_for_update()
    )
    item = db.scalar(
        select(BusinessVerification)
        .where(BusinessVerification.id == submission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    independent_reviewer(db, user, item)
    if item.status != "APPROVED" or latest_verification(db, organization).id != item.id:
        raise HTTPException(409, "Only the current approved verification can be revoked")
    _verify_recent_mfa(user, data.totp_code)
    item.status, item.review_reason = "REVOKED", data.reason
    item.reviewed_by, item.reviewed_at = user.id, datetime.now(timezone.utc)
    organization.verification_level = 0
    retire_active_certificates(db, organization)
    audit(db, request, user, item, "REVOKE_BUSINESS_VERIFICATION")
    db.commit()
    return item
