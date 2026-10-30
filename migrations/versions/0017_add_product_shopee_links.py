"""Add shopee_url and shopee_affiliate_url to products

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-09 00:00:00.000000

Adds nullable marketplace link columns to the products table.
shopee_url is managed by admins; shopee_affiliate_url is internal-only.
"""

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def _column_exists(table: str, column: str) -> bool:
    if _is_offline():
        return False
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade():
    if not _column_exists("products", "shopee_url"):
        op.add_column(
            "products",
            sa.Column("shopee_url", sa.String(length=1000), nullable=True),
        )
    if not _column_exists("products", "shopee_affiliate_url"):
        op.add_column(
            "products",
            sa.Column("shopee_affiliate_url", sa.String(length=1000), nullable=True),
        )


def downgrade():
    if _column_exists("products", "shopee_affiliate_url"):
        op.drop_column("products", "shopee_affiliate_url")
    if _column_exists("products", "shopee_url"):
        op.drop_column("products", "shopee_url")
