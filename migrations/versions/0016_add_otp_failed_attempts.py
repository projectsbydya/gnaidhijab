"""Add failed_attempts column to password_resets

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-05 00:00:00.000000

Adds failed_attempts (INTEGER NOT NULL DEFAULT 0) to password_resets so that
OTP brute-force attempts are counted per reset token. Existing rows are safe:
server_default=0 means no rows are invalidated.
"""

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _is_offline() -> bool:
    return context.is_offline_mode()


def _column_exists(table: str, column: str) -> bool:
    if _is_offline():
        return False
    return column in [c["name"] for c in inspect(op.get_bind()).get_columns(table)]


def upgrade():
    if not _column_exists("password_resets", "failed_attempts"):
        op.add_column(
            "password_resets",
            sa.Column(
                "failed_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade():
    if _is_offline() or _column_exists("password_resets", "failed_attempts"):
        op.drop_column("password_resets", "failed_attempts")
