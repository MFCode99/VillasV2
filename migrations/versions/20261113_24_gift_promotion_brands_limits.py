"""Add brand eligibility and configurable gift redemption limits.

Revision ID: 20261113_24
Revises: 20261113_23
"""

from alembic import op
import sqlalchemy as sa


revision = '20261113_24'
down_revision = '20261113_23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gift_promotions', sa.Column('eligibility_mode', sa.String(length=20), server_default='products', nullable=False))
    op.add_column('gift_promotions', sa.Column('eligible_brands_json', sa.JSON(), nullable=True))
    op.execute("UPDATE gift_promotions SET eligible_brands_json = JSON_ARRAY() WHERE eligible_brands_json IS NULL")
    op.alter_column('gift_promotions', 'eligible_brands_json', existing_type=sa.JSON(), nullable=False)
    op.add_column('gift_promotions', sa.Column('max_redemptions_per_user', sa.Integer(), server_default='1', nullable=False))
    op.drop_constraint('uq_gift_promotion_redemptions_promotion_user', 'gift_promotion_redemptions', type_='unique')


def downgrade() -> None:
    op.create_unique_constraint('uq_gift_promotion_redemptions_promotion_user', 'gift_promotion_redemptions', ['promotion_id', 'user_id'])
    op.drop_column('gift_promotions', 'max_redemptions_per_user')
    op.drop_column('gift_promotions', 'eligible_brands_json')
    op.drop_column('gift_promotions', 'eligibility_mode')
