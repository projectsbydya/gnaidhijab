"""Add background_image column to cta_settings

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Add background_image column to cta_settings
    conn = op.get_bind()
    if conn.dialect.name == 'mysql':
        # Check if column exists before adding
        result = conn.execute(
            sa.text("""SELECT COUNT(*) FROM information_schema.COLUMNS 
               WHERE TABLE_SCHEMA = DATABASE()
               AND TABLE_NAME = 'cta_settings' 
               AND COLUMN_NAME = 'background_image'""")
        ).scalar()
        if result == 0:
            op.add_column('cta_settings', sa.Column('background_image', sa.String(255), nullable=True))
    else:
        # For other dialects, try to add (will error if exists, wrapped in try)
        try:
            op.add_column('cta_settings', sa.Column('background_image', sa.String(255), nullable=True))
        except Exception:
            pass


def downgrade():
    # Remove background_image column
    try:
        op.drop_column('cta_settings', 'background_image')
    except Exception:
        pass
