"""Allow configurable minimum totals for dynamic catalogs.

Revision ID: 20261031_13
Revises: 20261031_12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261031_13'
down_revision = '20261031_12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in inspect(bind).get_columns('catalogs')}
    if 'minimum_total' not in columns:
        op.add_column('catalogs', sa.Column('minimum_total', sa.Numeric(12, 2), nullable=False, server_default='0.00'))
    op.execute("UPDATE catalogs SET minimum_total = 250.00 WHERE slug = 'villas' AND minimum_total = 0")
    op.execute("UPDATE catalogs SET minimum_total = 300.00 WHERE slug = 'interpilhas' AND minimum_total = 0")


def downgrade() -> None:
    columns = {column['name'] for column in inspect(op.get_bind()).get_columns('catalogs')}
    if 'minimum_total' in columns:
        op.drop_column('catalogs', 'minimum_total')
