"""Add selectable icons to categories.

Revision ID: 20261107_17
Revises: 20261106_16
"""

from alembic import op
import sqlalchemy as sa


revision = '20261107_17'
down_revision = '20261106_16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('icon', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('categories', 'icon')
