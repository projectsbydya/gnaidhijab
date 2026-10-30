"""Add color_image_path to product_variants

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-31 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006"
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    # Add color_image_path column to product_variants table
    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('color_image_path', sa.String(length=255), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # Drop color_image_path column from product_variants table
    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.drop_column('color_image_path')

    # ### end Alembic commands ###
