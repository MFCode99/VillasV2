"""Preserve three-decimal Interpilhas unit prices.

Revision ID: 20261029_10
Revises: 20261029_09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20261029_10'
down_revision = '20261029_09'
branch_labels = None
depends_on = None


EXTRA_CATEGORY = {
    'slug': 'interpilhas-colas-especiais-universais',
    'catalog_slug': 'interpilhas',
    'parent_slug': 'interpilhas-colas-adesivos',
    'label': 'Colas especiais e universais',
    'sort_order': 38,
    'active': True,
    'visible_on_site': True,
}


def _alter_unit_prices(scale: int) -> None:
    bind = op.get_bind()
    target = sa.Numeric(10, scale)
    source = sa.Numeric(10, 2 if scale == 3 else 3)
    if bind.dialect.name == 'sqlite':
        for table_name, column_name in (
            ('products', 'price'),
            ('cart_items', 'unit_price_snapshot'),
            ('order_lines', 'unit_price'),
        ):
            with op.batch_alter_table(table_name) as batch:
                batch.alter_column(column_name, existing_type=source, type_=target, existing_nullable=False)
        return
    op.alter_column('products', 'price', existing_type=source, type_=target, existing_nullable=False)
    op.alter_column('cart_items', 'unit_price_snapshot', existing_type=source, type_=target, existing_nullable=False)
    op.alter_column('order_lines', 'unit_price', existing_type=source, type_=target, existing_nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    categories = sa.table(
        'categories',
        sa.column('slug', sa.String(length=80)),
        sa.column('catalog_slug', sa.String(length=80)),
        sa.column('parent_slug', sa.String(length=80)),
        sa.column('label', sa.String(length=120)),
        sa.column('sort_order', sa.Integer()),
        sa.column('active', sa.Boolean()),
        sa.column('visible_on_site', sa.Boolean()),
    )
    exists = bind.execute(sa.select(categories.c.slug).where(categories.c.slug == EXTRA_CATEGORY['slug'])).first()
    if exists is None:
        bind.execute(categories.insert().values(**EXTRA_CATEGORY))
    _alter_unit_prices(3)


def downgrade() -> None:
    _alter_unit_prices(2)
    bind = op.get_bind()
    categories = sa.table('categories', sa.column('slug', sa.String(length=80)))
    bind.execute(categories.delete().where(categories.c.slug == EXTRA_CATEGORY['slug']))
