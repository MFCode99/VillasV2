"""Add campaign images and customer audience groups.

Revision ID: 20261107_18
Revises: 20261107_17
"""

from alembic import op
import sqlalchemy as sa


revision = '20261107_18'
down_revision = '20261107_17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('image_path', sa.String(length=255), nullable=True))
    op.add_column('campaigns', sa.Column('image_checksum', sa.String(length=64), nullable=True))
    op.add_column('campaigns', sa.Column('image_mime_type', sa.String(length=100), nullable=True))
    op.create_table(
        'customer_groups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'customer_group_members',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['customer_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
    )
    op.create_table(
        'campaign_customer_groups',
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['customer_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('campaign_id', 'group_id'),
    )


def downgrade() -> None:
    op.drop_table('campaign_customer_groups')
    op.drop_table('customer_group_members')
    op.drop_table('customer_groups')
    op.drop_column('campaigns', 'image_mime_type')
    op.drop_column('campaigns', 'image_checksum')
    op.drop_column('campaigns', 'image_path')
