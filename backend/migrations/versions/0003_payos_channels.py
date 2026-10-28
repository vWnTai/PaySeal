"""Encrypted tenant-bound payOS channels and receivables; additive upgrade."""

import sqlalchemy as sa
from alembic import op

revision = "0003_payos_channels"
down_revision = "0002_verification_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # Initial legacy migration calls create_all, so fresh installs already contain these.
    if not inspector.has_table("payment_channels"):
        op.create_table(
            "payment_channels",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("purpose", sa.String(16), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("credentials_ciphertext", sa.LargeBinary(), nullable=False),
            sa.Column("account_ciphertext", sa.LargeBinary(), nullable=False),
            sa.Column("account_last4", sa.String(4), nullable=False),
            sa.Column("bank_bin", sa.String(6), nullable=False),
            sa.Column("account_name", sa.String(200), nullable=False),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("collections"):
        op.create_table(
            "collections",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "channel_id", sa.Uuid(), sa.ForeignKey("payment_channels.id"), nullable=False
            ),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(128), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("order_code", sa.BigInteger(), nullable=False, unique=True),
            sa.Column("invoice_reference", sa.String(160), nullable=False),
            sa.Column("amount_minor", sa.BigInteger(), nullable=False),
            sa.Column("amount_paid", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, index=True),
            sa.Column("payment_link_id", sa.String(100)),
            sa.Column("checkout_url", sa.String(500)),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reconciled_at", sa.DateTime(timezone=True)),
            sa.Column("reconciliation_attempted_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "idempotency_key"),
        )
    columns = {c["name"] for c in inspector.get_columns("transfers")}
    if "channel_id" not in columns:
        op.add_column("transfers", sa.Column("channel_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_transfers_channel", "transfers", "payment_channels", ["channel_id"], ["id"]
        )
    if "dispatched_at" not in columns:
        op.add_column("transfers", sa.Column("dispatched_at", sa.DateTime(timezone=True)))
    if "reconciliation_attempted_at" not in columns:
        op.add_column(
            "transfers", sa.Column("reconciliation_attempted_at", sa.DateTime(timezone=True))
        )


def downgrade() -> None:
    raise RuntimeError(
        "Payment history must be preserved; restore a validated backup to roll back."
    )
