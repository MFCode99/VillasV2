"""Add configurable one-time gift promotions.

Revision ID: 20261112_21
Revises: 20261107_20
"""

from alembic import op
import sqlalchemy as sa


revision = '20261112_21'
down_revision = '20261107_20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('gift_only', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    op.create_index('ix_products_gift_only', 'products', ['gift_only'])
    op.create_table(
        'gift_promotions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('catalog_slug', sa.String(length=80), nullable=False),
        sa.Column('condition_type', sa.String(length=20), server_default='quantity', nullable=False),
        sa.Column('threshold_quantity', sa.Integer(), nullable=True),
        sa.Column('threshold_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('gift_product_ref', sa.String(length=80), nullable=False),
        sa.Column('gift_quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['catalog_slug'], ['catalogs.slug']),
        sa.ForeignKeyConstraint(['gift_product_ref'], ['products.ref']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gift_promotions_catalog_slug', 'gift_promotions', ['catalog_slug'])
    op.create_index('ix_gift_promotions_gift_product_ref', 'gift_promotions', ['gift_product_ref'])
    op.create_index('ix_gift_promotions_active', 'gift_promotions', ['active'])
    op.create_index('ix_gift_promotions_starts_at', 'gift_promotions', ['starts_at'])
    op.create_index('ix_gift_promotions_ends_at', 'gift_promotions', ['ends_at'])
    op.create_table(
        'gift_promotion_products',
        sa.Column('promotion_id', sa.Integer(), nullable=False),
        sa.Column('product_ref', sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(['promotion_id'], ['gift_promotions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_ref'], ['products.ref'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('promotion_id', 'product_ref'),
    )
    op.create_table(
        'gift_promotion_redemptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('promotion_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['promotion_id'], ['gift_promotions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('promotion_id', 'user_id', name='uq_gift_promotion_redemptions_promotion_user'),
    )
    op.create_index('ix_gift_promotion_redemptions_promotion_id', 'gift_promotion_redemptions', ['promotion_id'])
    op.create_index('ix_gift_promotion_redemptions_user_id', 'gift_promotion_redemptions', ['user_id'])
    op.create_index('ix_gift_promotion_redemptions_order_id', 'gift_promotion_redemptions', ['order_id'])


def downgrade() -> None:
    op.drop_table('gift_promotion_redemptions')
    op.drop_table('gift_promotion_products')
    op.drop_table('gift_promotions')
    op.drop_index('ix_products_gift_only', table_name='products')
    op.drop_column('products', 'gift_only')
