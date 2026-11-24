"""Add reversible product import history.

Revision ID: 20261116_25
Revises: 20261113_24
"""

from alembic import op
import sqlalchemy as sa


revision = '20261116_25'
down_revision = '20261113_24'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_import_batches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('actor_username', sa.String(length=80), nullable=False),
        sa.Column('catalog_slug', sa.String(length=80), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=32), server_default='spreadsheet', nullable=False),
        sa.Column('created_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('skipped_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('changes_json', sa.JSON(), nullable=False),
        sa.Column('created_categories_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=24), server_default='applied', nullable=False),
        sa.Column('rollback_summary_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('rolled_back_at', sa.DateTime(), nullable=True),
        sa.Column('rolled_back_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rolled_back_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_product_import_batches_actor_user_id', 'product_import_batches', ['actor_user_id'])
    op.create_index('ix_product_import_batches_catalog_slug', 'product_import_batches', ['catalog_slug'])
    op.create_index('ix_product_import_batches_status', 'product_import_batches', ['status'])
    op.create_index('ix_product_import_batches_created_at', 'product_import_batches', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_product_import_batches_created_at', table_name='product_import_batches')
    op.drop_index('ix_product_import_batches_status', table_name='product_import_batches')
    op.drop_index('ix_product_import_batches_catalog_slug', table_name='product_import_batches')
    op.drop_index('ix_product_import_batches_actor_user_id', table_name='product_import_batches')
    op.drop_table('product_import_batches')
