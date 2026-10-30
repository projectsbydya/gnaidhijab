"""Add price snapshot columns to order_items

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-28 00:00:00.000000

Adds original_price and discount_amount to order_items to snapshot
the pre-discount price and the per-unit saving at the time of purchase.
Both columns are nullable with DEFAULT 0 so existing rows remain valid.
"""

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def _column_exists(table: str, column: str) -> bool:
    if _is_offline():
        return False
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade():
    if not _column_exists("order_items", "original_price"):
        op.add_column(
            "order_items",
            sa.Column("original_price", sa.Integer, nullable=True, server_default="0"),
        )
    if not _column_exists("order_items", "discount_amount"):
        op.add_column(
            "order_items",
            sa.Column("discount_amount", sa.Integer, nullable=True, server_default="0"),
        )


def downgrade():
    if _is_offline() or _column_exists("order_items", "discount_amount"):
        op.drop_column("order_items", "discount_amount")
    if _is_offline() or _column_exists("order_items", "original_price"):
        op.drop_column("order_items", "original_price")
