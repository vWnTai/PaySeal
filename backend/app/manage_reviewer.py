"""Server-operator-only reviewer provisioning. Never exposed through a public API."""

import argparse
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.services.audit import add_audit_event


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant/revoke independent PaySeal reviewer access")
    parser.add_argument("email")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.email == args.email.strip().lower()).with_for_update()
        )
        if user is None or not user.is_active:
            parser.error("Register an active account first; no account is created by this command.")
        user.is_platform_reviewer = args.grant
        add_audit_event(
            db,
            organization_id=None,
            actor_id=None,
            event_type="GRANT_PLATFORM_REVIEWER" if args.grant else "REVOKE_PLATFORM_REVIEWER",
            object_type="user",
            object_id=str(user.id),
            data={"server_operator": True},
            correlation_id=str(uuid.uuid4()),
        )
        db.commit()
        print("Reviewer permission updated. MFA is mandatory for reviewer access.")


if __name__ == "__main__":
    main()
