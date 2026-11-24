"""Partition the user cart revision by catalog.

Revision ID: 20261029_11
Revises: 20261029_10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20261029_11'
down_revision = '20261029_10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in inspect(bind).get_columns('carts')}
    if 'catalog_revisions_json' not in columns:
        op.add_column('carts', sa.Column('catalog_revisions_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in inspect(bind).get_columns('carts')}
    if 'catalog_revisions_json' in columns:
        op.drop_column('carts', 'catalog_revisions_json')
