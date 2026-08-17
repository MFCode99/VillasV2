"""add internal admin notes to users

Revision ID: 20260816_07
Revises: 20260816_06
Create Date: 2026-08-16 21:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260816_07'
down_revision = '20260816_06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('admin_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'admin_notes')
