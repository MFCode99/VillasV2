"""phase 3 catalog and media foundations

Revision ID: 20260814_02
Revises: 20260814_01
Create Date: 2026-08-14 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260814_02'
down_revision = '20260814_01'
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {col['name'] for col in inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {idx['name'] for idx in inspect(bind).get_indexes(table_name)}


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _indexes(bind, table_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()

    _add_column_if_missing(bind, 'products', sa.Column('image_mime_type', sa.String(length=100), nullable=True))

    op.execute(sa.text("UPDATE products SET season='ambos' WHERE season IS NULL OR season='' OR season IN ('both', 'all', 'all-season')"))
    op.execute(sa.text("ALTER TABLE products MODIFY price DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE products MODIFY pvp DECIMAL(10,2) NULL"))
    op.execute(sa.text("ALTER TABLE products MODIFY season VARCHAR(20) NOT NULL DEFAULT 'ambos'"))
    op.execute(sa.text("ALTER TABLE cart_items MODIFY unit_price_snapshot DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE cart_items MODIFY line_total_snapshot DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE orders MODIFY subtotal DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE orders MODIFY total DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE order_lines MODIFY unit_price DECIMAL(10,2) NOT NULL"))
    op.execute(sa.text("ALTER TABLE order_lines MODIFY line_total DECIMAL(10,2) NOT NULL"))

    _create_index_if_missing(bind, 'ix_products_season', 'products', ['season'])
    _create_index_if_missing(bind, 'ix_products_active', 'products', ['active'])
    _create_index_if_missing(bind, 'ix_products_quantity_step', 'products', ['quantity_step'])
    _create_index_if_missing(bind, 'ix_categories_active', 'categories', ['active'])


def downgrade() -> None:
    bind = op.get_bind()

    if 'ix_categories_active' in _indexes(bind, 'categories'):
        op.drop_index('ix_categories_active', table_name='categories')
    if 'ix_products_quantity_step' in _indexes(bind, 'products'):
        op.drop_index('ix_products_quantity_step', table_name='products')
    if 'ix_products_active' in _indexes(bind, 'products'):
        op.drop_index('ix_products_active', table_name='products')
    if 'ix_products_season' in _indexes(bind, 'products'):
        op.drop_index('ix_products_season', table_name='products')

    op.execute(sa.text("ALTER TABLE order_lines MODIFY line_total DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE order_lines MODIFY unit_price DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE orders MODIFY total DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE orders MODIFY subtotal DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE cart_items MODIFY line_total_snapshot DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE cart_items MODIFY unit_price_snapshot DOUBLE NOT NULL"))
    op.execute(sa.text("ALTER TABLE products MODIFY pvp DOUBLE NULL"))
    op.execute(sa.text("ALTER TABLE products MODIFY price DOUBLE NOT NULL"))
    op.execute(sa.text("UPDATE products SET season='both' WHERE season='ambos'"))
    op.execute(sa.text("ALTER TABLE products MODIFY season VARCHAR(20) NOT NULL DEFAULT 'both'"))

    if 'image_mime_type' in _columns(bind, 'products'):
        op.drop_column('products', 'image_mime_type')
