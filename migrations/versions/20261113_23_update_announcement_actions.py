"""Track whether an admin ignored or read an update announcement.

Revision ID: 20261113_23
Revises: 20261112_22
"""

from alembic import op
import sqlalchemy as sa


revision = '20261113_23'
down_revision = '20261112_22'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('update_announcement_receipts', sa.Column('ignored_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('update_announcement_receipts', 'ignored_at')
