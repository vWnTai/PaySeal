from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.audit import add_audit_event
from app.services.verification import (
    find_public_payment,
    verify_document,
    verify_payment,
)

router = APIRouter(prefix="/public/verify", tags=["Public verification"])


def _find(db: Session, token: str):
    if len(token) < 22 or len(token) > 128:
        raise HTTPException(404, "Verification record not found")
    payment = find_public_payment(db, token)
    if payment is None:
        raise HTTPException(404, "Verification record not found")
    return payment


@router.get("/{token}")
def public_verify(token: str, request: Request, db: Session = Depends(get_db)):
    payment = _find(db, token)
    result = verify_payment(db, payment)
    add_audit_event(
        db,
        organization_id=payment.organization_id,
        actor_id=None,
        event_type="VERIFY_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"status": result["status"]},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return result


@router.post("/{token}/document")
async def public_verify_document(
    token: str,
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if document.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(415, "Only PDF uploads are accepted")
    chunks: list[bytes] = []
    size = 0
    while chunk := await document.read(1024 * 1024):
        size += len(chunk)
        if size > settings.max_pdf_bytes:
            raise HTTPException(413, "PDF exceeds upload limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Invalid PDF magic bytes")
    payment = _find(db, token)
    result = verify_document(db, payment, data)
    add_audit_event(
        db,
        organization_id=payment.organization_id,
        actor_id=None,
        event_type="VERIFY_PAYMENT",
        object_type="payment_request",
        object_id=str(payment.id),
        data={"document_integrity": result["document_integrity"]},
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    return result
