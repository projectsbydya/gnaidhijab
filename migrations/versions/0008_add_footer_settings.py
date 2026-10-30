"""Add footer_settings table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "footer_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("about_text", sa.Text(), nullable=True),
        sa.Column("operating_hours", sa.String(length=255), nullable=True),
        sa.Column("copyright_text", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("footer_settings")
