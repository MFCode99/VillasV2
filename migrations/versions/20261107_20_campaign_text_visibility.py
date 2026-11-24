"""Add campaign text visibility.

Revision ID: 20261107_20
Revises: 20261107_19
"""

from alembic import op
import sqlalchemy as sa


revision = '20261107_20'
down_revision = '20261107_19'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('show_text', sa.Boolean(), server_default=sa.text('1'), nullable=False))


def downgrade() -> None:
    op.drop_column('campaigns', 'show_text')
