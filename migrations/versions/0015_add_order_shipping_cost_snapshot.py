"""Add shipping cost snapshot columns to orders

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-03 00:00:00.000000

Adds original_shipping_cost and shipping_discount_amount to orders so the
pre-discount shipping cost and the applied shipping discount are snapshotted
at checkout time. Both columns are non-nullable with DEFAULT 0 so existing
rows remain valid and future rows cannot leave them NULL.
"""

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def _column_exists(table: str, column: str) -> bool:
    if _is_offline():
        return False
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade():
    if not _column_exists("orders", "original_shipping_cost"):
        op.add_column(
            "orders",
            sa.Column("original_shipping_cost", sa.Integer, nullable=False, server_default="0"),
        )
    if not _column_exists("orders", "shipping_discount_amount"):
        op.add_column(
            "orders",
            sa.Column("shipping_discount_amount", sa.Integer, nullable=False, server_default="0"),
        )


def downgrade():
    if _is_offline() or _column_exists("orders", "shipping_discount_amount"):
        op.drop_column("orders", "shipping_discount_amount")
    if _is_offline() or _column_exists("orders", "original_shipping_cost"):
        op.drop_column("orders", "original_shipping_cost")
