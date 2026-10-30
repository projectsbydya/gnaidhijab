"""Add sizes field to products

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-07 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009"
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    # Add sizes column to products table
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sizes', sa.String(length=200), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # Drop sizes column from products table
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('sizes')

    # ### end Alembic commands ###
