"""Add customer delivery address fields and align utility order steps.

Revision ID: 20261103_14
Revises: 20261031_13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261103_14'
down_revision = '20261031_13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in inspect(bind).get_columns('users')}
    additions = (
        ('delivery_address_line1', sa.String(length=150)),
        ('delivery_address_line2', sa.String(length=150)),
        ('delivery_postal_code', sa.String(length=20)),
        ('delivery_city', sa.String(length=120)),
        ('delivery_country', sa.String(length=120)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column('users', sa.Column(name, column_type, nullable=True))
    op.execute(
        "UPDATE products SET quantity_step = case_inner "
        "WHERE catalog_slug = 'interpilhas' AND case_inner IS NOT NULL AND case_inner > 0"
    )


def downgrade() -> None:
    columns = {column['name'] for column in inspect(op.get_bind()).get_columns('users')}
    for name in (
        'delivery_country', 'delivery_city', 'delivery_postal_code',
        'delivery_address_line2', 'delivery_address_line1',
    ):
        if name in columns:
            op.drop_column('users', name)
