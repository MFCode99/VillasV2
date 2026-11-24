"""Add catalog partitions and Interpilhas category hierarchy.

Revision ID: 20261029_09
Revises: 20260816_08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20261029_09'
down_revision = '20260816_08'
branch_labels = None
depends_on = None


CATALOGS = (
    {
        'slug': 'villas',
        'label': 'Villas',
        'description': 'Catálogo têxtil Villas.',
        'icon': 'mdi-hanger',
        'sort_order': 0,
        'active': True,
    },
    {
        'slug': 'interpilhas',
        'label': 'Interpilhas',
        'description': 'Pilhas, ambientadores, colas e adesivos.',
        'icon': 'mdi-battery-charging-medium',
        'sort_order': 10,
        'active': True,
    },
)


INTERPILHAS_CATEGORIES = (
    ('interpilhas-pilhas', None, 'Pilhas', 10),
    ('interpilhas-pilhas-alcalinas', 'interpilhas-pilhas', 'Alcalinas', 11),
    ('interpilhas-pilhas-zinco', 'interpilhas-pilhas', 'Zinco e Heavy Duty', 12),
    ('interpilhas-pilhas-litio', 'interpilhas-pilhas', 'Lítio', 13),
    ('interpilhas-pilhas-recarregaveis', 'interpilhas-pilhas', 'Recarregáveis', 14),
    ('interpilhas-pilhas-relogio', 'interpilhas-pilhas', 'Relógio', 15),
    ('interpilhas-pilhas-especiais', 'interpilhas-pilhas', 'Especiais', 16),
    ('interpilhas-ambientadores', None, 'Ambientadores', 20),
    ('interpilhas-ambientadores-mon-areon', 'interpilhas-ambientadores', 'Mon Areon', 21),
    ('interpilhas-ambientadores-smile', 'interpilhas-ambientadores', 'Smile', 22),
    ('interpilhas-ambientadores-fresco', 'interpilhas-ambientadores', 'Fresco', 23),
    ('interpilhas-ambientadores-fresh-wave', 'interpilhas-ambientadores', 'Fresh Wave', 24),
    ('interpilhas-ambientadores-smile-toy', 'interpilhas-ambientadores', 'Smile Toy', 25),
    ('interpilhas-colas-adesivos', None, 'Colas e adesivos', 30),
    ('interpilhas-colas-instantaneas', 'interpilhas-colas-adesivos', 'Colas instantâneas', 31),
    ('interpilhas-colas-contacto', 'interpilhas-colas-adesivos', 'Colas de contacto', 32),
    ('interpilhas-silicones-selantes', 'interpilhas-colas-adesivos', 'Silicones e selantes', 33),
    ('interpilhas-massas-adesivas', 'interpilhas-colas-adesivos', 'Massas adesivas', 34),
    ('interpilhas-fitas-adesivas', 'interpilhas-colas-adesivos', 'Fitas adesivas', 35),
    ('interpilhas-escolar-escritorio', 'interpilhas-colas-adesivos', 'Escolar e escritório', 36),
    ('interpilhas-ferramentas-acessorios', 'interpilhas-colas-adesivos', 'Ferramentas e acessórios', 37),
)


def _columns(bind, table_name: str) -> set[str]:
    return {column['name'] for column in inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {index['name'] for index in inspect(bind).get_indexes(table_name)}


def _foreign_keys(bind, table_name: str) -> set[str]:
    return {item['name'] for item in inspect(bind).get_foreign_keys(table_name) if item.get('name')}


def _add_column(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def _add_index(bind, name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(bind, table_name):
        op.create_index(name, table_name, columns)


def _insert_missing(bind, table, key: str, rows) -> None:
    for row in rows:
        exists = bind.execute(sa.select(table.c[key]).where(table.c[key] == row[key])).first()
        if exists is None:
            bind.execute(table.insert().values(**row))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'catalogs' not in inspector.get_table_names():
        op.create_table(
            'catalogs',
            sa.Column('slug', sa.String(length=80), primary_key=True),
            sa.Column('label', sa.String(length=120), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('icon', sa.String(length=80), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    catalogs = sa.table(
        'catalogs',
        sa.column('slug', sa.String(length=80)),
        sa.column('label', sa.String(length=120)),
        sa.column('description', sa.Text()),
        sa.column('icon', sa.String(length=80)),
        sa.column('sort_order', sa.Integer()),
        sa.column('active', sa.Boolean()),
    )
    _insert_missing(bind, catalogs, 'slug', CATALOGS)

    _add_column(bind, 'categories', sa.Column('catalog_slug', sa.String(length=80), nullable=True))
    _add_column(bind, 'categories', sa.Column('parent_slug', sa.String(length=80), nullable=True))
    bind.execute(sa.text("UPDATE categories SET catalog_slug='villas' WHERE catalog_slug IS NULL OR catalog_slug=''"))
    op.alter_column('categories', 'catalog_slug', existing_type=sa.String(length=80), nullable=False, server_default='villas')
    _add_index(bind, 'ix_categories_catalog_slug', 'categories', ['catalog_slug'])
    _add_index(bind, 'ix_categories_parent_slug', 'categories', ['parent_slug'])
    category_fks = _foreign_keys(bind, 'categories')
    if 'fk_categories_catalog_slug_catalogs' not in category_fks:
        op.create_foreign_key('fk_categories_catalog_slug_catalogs', 'categories', 'catalogs', ['catalog_slug'], ['slug'])
    if 'fk_categories_parent_slug_categories' not in category_fks:
        op.create_foreign_key('fk_categories_parent_slug_categories', 'categories', 'categories', ['parent_slug'], ['slug'], ondelete='SET NULL')

    _add_column(bind, 'products', sa.Column('catalog_slug', sa.String(length=80), nullable=True))
    _add_column(bind, 'products', sa.Column('brand', sa.String(length=80), nullable=True))
    _add_column(bind, 'products', sa.Column('family', sa.String(length=120), nullable=True))
    _add_column(bind, 'products', sa.Column('ean', sa.String(length=20), nullable=True))
    _add_column(bind, 'products', sa.Column('price_base', sa.Numeric(10, 3), nullable=True))
    _add_column(bind, 'products', sa.Column('eco_value', sa.Numeric(10, 3), nullable=False, server_default='0.000'))
    _add_column(bind, 'products', sa.Column('case_inner', sa.Integer(), nullable=True))
    _add_column(bind, 'products', sa.Column('case_outer', sa.Integer(), nullable=True))
    bind.execute(sa.text("UPDATE products SET catalog_slug='villas' WHERE catalog_slug IS NULL OR catalog_slug=''"))
    op.alter_column('products', 'catalog_slug', existing_type=sa.String(length=80), nullable=False, server_default='villas')
    _add_index(bind, 'ix_products_catalog_slug', 'products', ['catalog_slug'])
    _add_index(bind, 'ix_products_brand', 'products', ['brand'])
    _add_index(bind, 'ix_products_family', 'products', ['family'])
    _add_index(bind, 'ix_products_ean', 'products', ['ean'])
    product_fks = _foreign_keys(bind, 'products')
    if 'fk_products_catalog_slug_catalogs' not in product_fks:
        op.create_foreign_key('fk_products_catalog_slug_catalogs', 'products', 'catalogs', ['catalog_slug'], ['slug'])

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
    rows = (
        {
            'slug': slug,
            'catalog_slug': 'interpilhas',
            'parent_slug': parent_slug,
            'label': label,
            'sort_order': sort_order,
            'active': True,
            'visible_on_site': True,
        }
        for slug, parent_slug, label, sort_order in INTERPILHAS_CATEGORIES
    )
    _insert_missing(bind, categories, 'slug', rows)


def downgrade() -> None:
    bind = op.get_bind()
    categories = sa.table('categories', sa.column('catalog_slug', sa.String(length=80)))
    bind.execute(categories.delete().where(categories.c.catalog_slug == 'interpilhas'))

    product_fks = _foreign_keys(bind, 'products')
    if 'fk_products_catalog_slug_catalogs' in product_fks:
        op.drop_constraint('fk_products_catalog_slug_catalogs', 'products', type_='foreignkey')
    for name in ('ix_products_ean', 'ix_products_family', 'ix_products_brand', 'ix_products_catalog_slug'):
        if name in _indexes(bind, 'products'):
            op.drop_index(name, table_name='products')
    for name in ('case_outer', 'case_inner', 'eco_value', 'price_base', 'ean', 'family', 'brand', 'catalog_slug'):
        if name in _columns(bind, 'products'):
            op.drop_column('products', name)

    category_fks = _foreign_keys(bind, 'categories')
    for name in ('fk_categories_parent_slug_categories', 'fk_categories_catalog_slug_catalogs'):
        if name in category_fks:
            op.drop_constraint(name, 'categories', type_='foreignkey')
    for name in ('ix_categories_parent_slug', 'ix_categories_catalog_slug'):
        if name in _indexes(bind, 'categories'):
            op.drop_index(name, table_name='categories')
    for name in ('parent_slug', 'catalog_slug'):
        if name in _columns(bind, 'categories'):
            op.drop_column('categories', name)
    if 'catalogs' in inspect(bind).get_table_names():
        op.drop_table('catalogs')
