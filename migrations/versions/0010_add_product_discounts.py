"""Add product_discounts table

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-25 21:00:00.000000

Stores product-level discounts with support for nominal and percentage
values, active flag, and optional start/end period.
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def _table_exists(name: str) -> bool:
    if _is_offline():
        return False
    return inspect(op.get_bind()).has_table(name)


def _index_exists(table: str, index: str) -> bool:
    if _is_offline():
        return False
    return index in [i["name"] for i in inspect(op.get_bind()).get_indexes(table)]


def upgrade():
    if not _table_exists("product_discounts"):
        op.create_table(
            "product_discounts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "product_id",
                sa.Integer,
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(100), nullable=True),
            sa.Column("discount_type", sa.String(20), nullable=False),
            sa.Column("value", sa.Integer, nullable=False, default=0),
            sa.Column("is_active", sa.Boolean, default=True, nullable=True),
            sa.Column("starts_at", sa.DateTime, nullable=True),
            sa.Column("ends_at", sa.DateTime, nullable=True),
            sa.Column(
                "created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")
            ),
            sa.Column(
                "updated_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("NOW() ON UPDATE CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "value >= 0", name="ck_product_discounts_value_non_negative"
            ),
            sa.CheckConstraint(
                "discount_type IN ('percentage', 'fixed')",
                name="ck_product_discounts_type_allowed",
            ),
            sa.CheckConstraint(
                "(discount_type != 'percentage') OR (value BETWEEN 0 AND 100)",
                name="ck_product_discounts_percentage_range",
            ),
            sa.UniqueConstraint(
                "product_id", name="uq_product_discounts_product_id"
            ),
        )

    if _is_offline() or _table_exists("product_discounts"):
        if _is_offline() or not _index_exists(
            "product_discounts", "ix_product_discounts_active_dates"
        ):
            op.create_index(
                "ix_product_discounts_active_dates",
                "product_discounts",
                ["is_active", "starts_at", "ends_at"],
            )


def downgrade():
    if _is_offline() or _table_exists("product_discounts"):
        if _is_offline() or _index_exists(
            "product_discounts", "ix_product_discounts_active_dates"
        ):
            op.drop_index(
                "ix_product_discounts_active_dates", table_name="product_discounts"
            )
        op.drop_table("product_discounts")
