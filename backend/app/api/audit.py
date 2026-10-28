from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, require_roles
from app.core.database import get_db
from app.models.entities import AuditEvent, Role

router = APIRouter(prefix="/audit-events", tags=["Audit"])


@router.get("")
def list_audit_events(
    context: TenantContext = Depends(require_roles(Role.OWNER, Role.AUDITOR)),
    db: Session = Depends(get_db),
):
    values = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == context.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "id": item.id,
            "actor_id": item.actor_id,
            "event_type": item.event_type,
            "object_type": item.object_type,
            "object_id": item.object_id,
            "event_data": item.event_data,
            "previous_hash": item.previous_hash,
            "event_hash": item.event_hash,
            "created_at": item.created_at,
            "correlation_id": item.correlation_id,
        }
        for item in values
    ]
