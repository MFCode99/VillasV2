"""Add configurable campaign discounts.

Revision ID: 20261107_19
Revises: 20261107_18
"""

from alembic import op
import sqlalchemy as sa


revision = '20261107_19'
down_revision = '20261107_18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('discount_type', sa.String(length=20), server_default='none', nullable=False))
    op.add_column('campaigns', sa.Column('discount_value', sa.Numeric(10, 3), server_default='0.000', nullable=False))
    op.add_column('campaign_products', sa.Column('promotional_price', sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column('campaign_products', 'promotional_price')
    op.drop_column('campaigns', 'discount_value')
    op.drop_column('campaigns', 'discount_type')
