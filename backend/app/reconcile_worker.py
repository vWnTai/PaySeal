"""Read-only provider polling. Never creates or retries a financial instruction."""

import argparse
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.models.entities import Collection, Transfer
from app.services.live_payments import reconcile_live_transfer, reconcile_receivable

logger = logging.getLogger("payseal.reconciliation")


def reconcile_once() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    recent = now - timedelta(seconds=60)
    with SessionLocal() as db:
        transfers = db.scalars(
            select(Transfer.id)
            .where(
                Transfer.provider == "payos",
                or_(
                    Transfer.status.in_(["DISPATCHING", "UNKNOWN", "SUBMITTED", "ON_HOLD"]),
                    (Transfer.status == "SUCCEEDED")
                    & (Transfer.created_at > now - timedelta(days=30)),
                ),
                or_(
                    Transfer.reconciliation_attempted_at.is_(None),
                    Transfer.reconciliation_attempted_at < recent,
                ),
            )
            .order_by(Transfer.reconciliation_attempted_at.asc().nullsfirst(), Transfer.created_at)
            .limit(100)
        ).all()
        collections = db.scalars(
            select(Collection.id)
            .where(
                Collection.status.in_(
                    ["DISPATCHING", "UNKNOWN", "PENDING", "PROCESSING", "UNDERPAID"]
                ),
                or_(
                    Collection.reconciliation_attempted_at.is_(None),
                    Collection.reconciliation_attempted_at < recent,
                ),
            )
            .order_by(
                Collection.reconciliation_attempted_at.asc().nullsfirst(), Collection.created_at
            )
            .limit(100)
        ).all()
    counts = {"checked": 0, "unresolved": 0}
    for kind, identifiers in (("transfer", transfers), ("collection", collections)):
        for identifier in identifiers:
            with SessionLocal() as db:
                correlation = str(uuid.uuid4())
                try:
                    if kind == "transfer":
                        item = db.get(Transfer, identifier)
                        reconcile_live_transfer(db, item, None, correlation)
                    else:
                        item = db.get(Collection, identifier)
                        reconcile_receivable(db, item.id, item.organization_id, None, correlation)
                    counts["checked"] += 1
                except Exception:
                    db.rollback()
                    # Persist last-attempt time to avoid starving later records on repeated outages.
                    item = db.get(Transfer if kind == "transfer" else Collection, identifier)
                    if item:
                        item.reconciliation_attempted_at = now
                        db.commit()
                    counts["unresolved"] += 1
                    logger.warning(
                        "unresolved kind=%s id=%s correlation=%s; no instruction resubmitted",
                        kind,
                        identifier,
                        correlation,
                    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    arguments = parser.parse_args()
    if arguments.interval < 30:
        parser.error("interval must be at least 30 seconds")
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            logger.info("reconciliation summary=%s", reconcile_once())
        except Exception:
            logger.error("reconciliation unavailable; no provider instructions sent")
        if arguments.once:
            return
        time.sleep(arguments.interval)


if __name__ == "__main__":
    main()
