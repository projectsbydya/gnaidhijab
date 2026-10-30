"""Add 'cancelled' to order_status enum

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-28 00:00:00.000000

MySQL requires ALTER TABLE ... MODIFY COLUMN to extend an ENUM.
The new enum is: pending, paid, shipped, completed, cancelled.
"""

from alembic import op, context
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def upgrade():
    if _is_offline():
        return
    op.execute(
        "ALTER TABLE orders MODIFY COLUMN status "
        "ENUM('pending','paid','shipped','completed','cancelled') "
        "NOT NULL DEFAULT 'pending'"
    )


def downgrade():
    if _is_offline():
        return
    # Remove 'cancelled' — any existing cancelled rows must be handled first
    op.execute(
        "ALTER TABLE orders MODIFY COLUMN status "
        "ENUM('pending','paid','shipped','completed') "
        "NOT NULL DEFAULT 'pending'"
    )
