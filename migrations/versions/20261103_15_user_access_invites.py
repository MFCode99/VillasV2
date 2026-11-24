"""Add one-time user access invitations.

Revision ID: 20261103_15
Revises: 20261103_14
"""

from alembic import op
import sqlalchemy as sa

revision = '20261103_15'
down_revision = '20261103_14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_access_invites',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_user_access_invites_user_id', 'user_access_invites', ['user_id'])
    op.create_index('ix_user_access_invites_created_by_user_id', 'user_access_invites', ['created_by_user_id'])
    op.create_index('ix_user_access_invites_token_hash', 'user_access_invites', ['token_hash'])
    op.create_index('ix_user_access_invites_expires_at', 'user_access_invites', ['expires_at'])


def downgrade() -> None:
    op.drop_table('user_access_invites')
