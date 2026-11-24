"""Add configurable tiers to gift promotions.

Revision ID: 20261124_26
Revises: 20261116_25
"""

from alembic import op
import sqlalchemy as sa


revision = '20261124_26'
down_revision = '20261116_25'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gift_promotion_tiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('promotion_id', sa.Integer(), nullable=False),
        sa.Column('minimum_threshold', sa.Numeric(12, 3), nullable=False),
        sa.Column('maximum_threshold', sa.Numeric(12, 3), nullable=True),
        sa.Column('gift_product_ref', sa.String(length=80), nullable=False),
        sa.Column('gift_quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['gift_product_ref'], ['products.ref']),
        sa.ForeignKeyConstraint(['promotion_id'], ['gift_promotions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gift_promotion_tiers_promotion_id', 'gift_promotion_tiers', ['promotion_id'])
    op.create_index('ix_gift_promotion_tiers_gift_product_ref', 'gift_promotion_tiers', ['gift_product_ref'])
    op.execute(
        """
        INSERT INTO gift_promotion_tiers
            (promotion_id, minimum_threshold, maximum_threshold, gift_product_ref, gift_quantity, sort_order)
        SELECT
            id,
            CASE WHEN condition_type = 'value' THEN threshold_value ELSE threshold_quantity END,
            NULL,
            gift_product_ref,
            gift_quantity,
            0
        FROM gift_promotions
        """
    )


def downgrade() -> None:
    op.drop_index('ix_gift_promotion_tiers_gift_product_ref', table_name='gift_promotion_tiers')
    op.drop_index('ix_gift_promotion_tiers_promotion_id', table_name='gift_promotion_tiers')
    op.drop_table('gift_promotion_tiers')
