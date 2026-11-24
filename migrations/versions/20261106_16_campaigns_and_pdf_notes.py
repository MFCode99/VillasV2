"""Add campaigns and optional order PDF observations.

Revision ID: 20261106_16
Revises: 20261103_15
"""

from alembic import op
import sqlalchemy as sa


revision = '20261106_16'
down_revision = '20261103_15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('pdf_notes', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('include_pdf_notes', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    op.add_column('admin_order_drafts', sa.Column('pdf_notes', sa.Text(), nullable=True))
    op.add_column('admin_order_drafts', sa.Column('include_pdf_notes', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaigns_active', 'campaigns', ['active'])
    op.create_index('ix_campaigns_starts_at', 'campaigns', ['starts_at'])
    op.create_index('ix_campaigns_ends_at', 'campaigns', ['ends_at'])
    op.create_table(
        'campaign_products',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('product_ref', sa.String(length=80), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_ref'], ['products.ref'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'product_ref', name='uq_campaign_products_campaign_product'),
    )
    op.create_index('ix_campaign_products_campaign_id', 'campaign_products', ['campaign_id'])
    op.create_index('ix_campaign_products_product_ref', 'campaign_products', ['product_ref'])


def downgrade() -> None:
    op.drop_table('campaign_products')
    op.drop_table('campaigns')
    op.drop_column('admin_order_drafts', 'include_pdf_notes')
    op.drop_column('admin_order_drafts', 'pdf_notes')
    op.drop_column('orders', 'include_pdf_notes')
    op.drop_column('orders', 'pdf_notes')
