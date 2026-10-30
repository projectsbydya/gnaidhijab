"""Add product_slug_history table

Revision ID: 0002_add_product_slug_history
Revises: 0001_initial_schema
Create Date: 2026-05-11 00:00:00.000000

Stores every historical slug a product has ever used so that old inbound
links can be 301-redirected to the current canonical URL.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "0002_add_product_slug_history"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in Inspector.from_engine(op.get_bind()).get_table_names()


def _index_exists(table: str, index: str) -> bool:
    insp = Inspector.from_engine(op.get_bind())
    return index in [i["name"] for i in insp.get_indexes(table)]


def upgrade():
    if not _table_exists("product_slug_history"):
        op.create_table(
            "product_slug_history",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "product_id",
                sa.Integer,
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("slug", sa.String(220), nullable=False, unique=True),
            sa.Column(
                "replaced_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
        )

    if _table_exists("product_slug_history"):
        if not _index_exists("product_slug_history", "ix_psh_slug"):
            op.create_index("ix_psh_slug", "product_slug_history", ["slug"], unique=True)
        if not _index_exists("product_slug_history", "ix_psh_product_id"):
            op.create_index("ix_psh_product_id", "product_slug_history", ["product_id"])


def downgrade():
    if _table_exists("product_slug_history"):
        if _index_exists("product_slug_history", "ix_psh_slug"):
            op.drop_index("ix_psh_slug", table_name="product_slug_history")
        if _index_exists("product_slug_history", "ix_psh_product_id"):
            op.drop_index("ix_psh_product_id", table_name="product_slug_history")
        op.drop_table("product_slug_history")
