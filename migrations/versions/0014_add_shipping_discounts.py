"""Add shipping_discounts table

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-03 00:00:00.000000

Stores shipping-level discounts with support for fixed-amount discounts and
percentage-based discounts, minimum order threshold, optional maximum discount
cap, active flag, and optional start/end period.
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0014"
down_revision = "0013"
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
    if not _table_exists("shipping_discounts"):
        op.create_table(
            "shipping_discounts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(100), nullable=True),
            sa.Column("discount_type", sa.String(20), nullable=False),
            sa.Column("value", sa.Integer, nullable=False, default=0),
            sa.Column("minimum_order_amount", sa.Integer, nullable=False, default=0),
            sa.Column("maximum_discount_amount", sa.Integer, nullable=True),
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
                "value >= 0", name="ck_shipping_discounts_value_non_negative"
            ),
            sa.CheckConstraint(
                "discount_type IN ('fixed', 'percentage')",
                name="ck_shipping_discounts_type_allowed",
            ),
            sa.CheckConstraint(
                "(discount_type != 'percentage') OR (value BETWEEN 0 AND 100)",
                name="ck_shipping_discounts_percentage_range",
            ),
            sa.CheckConstraint(
                "minimum_order_amount >= 0",
                name="ck_shipping_discounts_min_order_non_negative",
            ),
            sa.CheckConstraint(
                "(maximum_discount_amount IS NULL) OR (maximum_discount_amount >= 0)",
                name="ck_shipping_discounts_max_discount_non_negative",
            ),
            sa.CheckConstraint(
                "(maximum_discount_amount IS NULL) OR (discount_type != 'fixed') OR (maximum_discount_amount >= value)",
                name="ck_shipping_discounts_fixed_max_ge_value",
            ),
            sa.CheckConstraint(
                "(ends_at IS NULL) OR (starts_at IS NULL) OR (ends_at >= starts_at)",
                name="ck_shipping_discounts_dates",
            ),
        )

    if _is_offline() or _table_exists("shipping_discounts"):
        if _is_offline() or not _index_exists(
            "shipping_discounts", "ix_shipping_discounts_active_dates"
        ):
            op.create_index(
                "ix_shipping_discounts_active_dates",
                "shipping_discounts",
                ["is_active", "starts_at", "ends_at"],
            )


def downgrade():
    if _is_offline() or _table_exists("shipping_discounts"):
        if _is_offline() or _index_exists(
            "shipping_discounts", "ix_shipping_discounts_active_dates"
        ):
            op.drop_index(
                "ix_shipping_discounts_active_dates", table_name="shipping_discounts"
            )
        op.drop_table("shipping_discounts")
