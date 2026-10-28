"""Business verification and durable sandbox transfers; preserves existing data."""

import sqlalchemy as sa
from alembic import op

revision = "0002_verification_transfers"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # The legacy initial migration uses create_all; handle fresh installs as well.
    if "is_platform_reviewer" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column(
            "users",
            sa.Column(
                "is_platform_reviewer", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if not inspector.has_table("business_verifications"):
        op.create_table(
            "business_verifications",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("submitted_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("profile", sa.JSON(), nullable=False),
            sa.Column("representative_name", sa.String(160), nullable=False),
            sa.Column("contact_email", sa.String(320), nullable=False),
            sa.Column("registered_address", sa.String(500), nullable=False),
            sa.Column("registration_number", sa.String(100), nullable=False),
            sa.Column("document_object_key", sa.String(200), nullable=False),
            sa.Column("document_sha256", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, index=True),
            sa.Column("review_reason", sa.String(1000)),
            sa.Column("review_checks", sa.JSON()),
            sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.Column("valid_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("transfers"):
        op.create_table(
            "transfers",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "payment_request_id",
                sa.Uuid(),
                sa.ForeignKey("payment_requests.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("payment_version", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(128), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("provider_reference", sa.String(100), nullable=False, unique=True),
            sa.Column("status", sa.String(24), nullable=False, index=True),
            sa.Column("amount_minor", sa.BigInteger(), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("beneficiary_name", sa.String(200), nullable=False),
            sa.Column("bank_code", sa.String(32), nullable=False),
            sa.Column("account_last4", sa.String(4), nullable=False),
            sa.Column("invoice_reference", sa.String(160), nullable=False),
            sa.Column("failure_reason", sa.String(500)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("reconciled_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("payment_request_id", "payment_version"),
            sa.UniqueConstraint("organization_id", "idempotency_key"),
        )
    if not inspector.has_table("sandbox_receipts"):
        op.create_table(
            "sandbox_receipts",
            sa.Column("provider_reference", sa.String(100), primary_key=True),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("amount_minor", sa.BigInteger(), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("transfer_events"):
        op.create_table(
            "transfer_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "transfer_id", sa.Uuid(), sa.ForeignKey("transfers.id"), nullable=False, index=True
            ),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    for table in ("transfer_events", "sandbox_receipts", "transfers", "business_verifications"):
        op.drop_table(table)
    op.drop_column("users", "is_platform_reviewer")
