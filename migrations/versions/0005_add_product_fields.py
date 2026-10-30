"""Add sold_count and dynamic content fields to products

Revision ID: 0005_sold_count_and_content_fields
Revises: 0004
Create Date: 2026-05-17 17:50:34.239065

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    # Add sold_count and dynamic content fields to products table
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sold_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('materials_care', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('shipping_returns', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('size_guide', sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # Drop sold_count and dynamic content fields from products table
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('size_guide')
        batch_op.drop_column('shipping_returns')
        batch_op.drop_column('materials_care')
        batch_op.drop_column('sold_count')

    # ### end Alembic commands ###
