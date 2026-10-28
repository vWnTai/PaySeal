from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto.canonical import canonicalize, sha256_hex
from app.models.entities import AuditEvent

SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "account_number",
    "refresh_token",
    "totp",
    "totp_code",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def add_audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    event_type: str,
    object_type: str,
    object_id: str,
    data: dict[str, Any],
    correlation_id: str,
) -> AuditEvent:
    previous = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    previous_hash = previous.event_hash if previous else "0" * 64
    safe_data = _redact(data)
    created_at = datetime.now(timezone.utc)
    canonical = {
        "organization_id": str(organization_id) if organization_id else None,
        "actor_id": str(actor_id) if actor_id else None,
        "event_type": event_type,
        "object_type": object_type,
        "object_id": object_id,
        "event_data": safe_data,
        "created_at": created_at.isoformat(),
        "correlation_id": correlation_id,
    }
    event = AuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        event_data=safe_data,
        previous_hash=previous_hash,
        event_hash=sha256_hex(bytes.fromhex(previous_hash) + canonicalize(canonical)),
        created_at=created_at,
        correlation_id=correlation_id,
    )
    db.add(event)
    return event
