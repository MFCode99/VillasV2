"""allow shared email addresses between users

Revision ID: 20260816_06
Revises: 20260814_05
Create Date: 2026-08-16 20:35:00.000000
"""

from alembic import op


revision = '20260816_06'
down_revision = '20260814_05'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
