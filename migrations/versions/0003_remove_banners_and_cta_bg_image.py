"""Remove banners table and cta_settings.background_image

Revision ID: 0003
Revises: 0002_add_product_slug_history
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002_add_product_slug_history'
branch_labels = None
depends_on = None


def upgrade():
    # Drop banners table if it exists
    op.execute(sa.text("DROP TABLE IF EXISTS banners"))
    
    # Remove background_image column from cta_settings if it exists
    conn = op.get_bind()
    if conn.dialect.name == 'mysql':
        # Check if column exists before dropping
        result = conn.execute(
            sa.text("""SELECT COUNT(*) FROM information_schema.COLUMNS 
               WHERE TABLE_SCHEMA = DATABASE()
               AND TABLE_NAME = 'cta_settings' 
               AND COLUMN_NAME = 'background_image'""")
        ).scalar()
        if result > 0:
            op.drop_column('cta_settings', 'background_image')
    else:
        # For other dialects, try to drop (will error if doesn't exist, wrapped in try)
        try:
            op.drop_column('cta_settings', 'background_image')
        except Exception:
            pass


def downgrade():
    # Restore background_image column
    op.add_column('cta_settings', sa.Column('background_image', sa.String(255), nullable=True))
    
    # Recreate banners table
    op.create_table(
        'banners',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image', sa.String(255), nullable=False),
        sa.Column('link', sa.String(255), nullable=True),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
