"""Add cancellation_reason column to orders

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-28 00:00:00.000000

Stores a machine-readable reason for why an order was cancelled
(e.g. expired_payment, system_cancelled). Nullable so existing rows
and non-cancelled orders are unaffected.
"""

from alembic import op, context
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _column_exists(table, column):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade():
    if context.is_offline_mode():
        return
    if not _column_exists("orders", "cancellation_reason"):
        op.add_column(
            "orders",
            sa.Column("cancellation_reason", sa.String(50), nullable=True),
        )


def downgrade():
    if context.is_offline_mode():
        return
    if _column_exists("orders", "cancellation_reason"):
        op.drop_column("orders", "cancellation_reason")
