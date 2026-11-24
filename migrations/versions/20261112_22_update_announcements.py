"""Add selectable update announcements and read receipts.

Revision ID: 20261112_22
Revises: 20261112_21
"""

from alembic import op
import sqlalchemy as sa


revision = '20261112_22'
down_revision = '20261112_21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'update_announcements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('channel', sa.String(length=32), server_default='stable', nullable=False),
        sa.Column('selected_notes_json', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_update_announcements_version', 'update_announcements', ['version'])
    op.create_index('ix_update_announcements_active', 'update_announcements', ['active'])
    op.create_index('ix_update_announcements_created_by_user_id', 'update_announcements', ['created_by_user_id'])
    op.create_table(
        'update_announcement_receipts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('announcement_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['announcement_id'], ['update_announcements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('announcement_id', 'user_id', name='uq_update_announcement_receipts_announcement_user'),
    )
    op.create_index('ix_update_announcement_receipts_announcement_id', 'update_announcement_receipts', ['announcement_id'])
    op.create_index('ix_update_announcement_receipts_user_id', 'update_announcement_receipts', ['user_id'])


def downgrade() -> None:
    op.drop_table('update_announcement_receipts')
    op.drop_table('update_announcements')
