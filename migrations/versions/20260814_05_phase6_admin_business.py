"""phase 6 admin and business operations

Revision ID: 20260814_05
Revises: 20260814_04
Create Date: 2026-08-15 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260814_05'
down_revision = '20260814_04'
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _columns(bind, table_name: str) -> set[str]:
    return {col['name'] for col in inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name: str) -> set[str]:
    return {idx['name'] for idx in inspect(bind).get_indexes(table_name)}


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name not in _indexes(bind, table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _create_table_if_missing(bind, table_name: str, columns: list[sa.Column], constraints: list[sa.Column | sa.Constraint]) -> None:
    if table_name not in _tables(bind):
        op.create_table(table_name, *columns, *constraints)


def upgrade() -> None:
    bind = op.get_bind()

    _add_column_if_missing(bind, 'users', sa.Column('nif', sa.String(length=20), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('created_by_user_id', sa.Integer(), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('origin', sa.String(length=32), nullable=False, server_default='client'))
    _add_column_if_missing(bind, 'orders', sa.Column('confirmed_at', sa.DateTime(), nullable=True))

    _create_index_if_missing(bind, 'ix_orders_created_by_user_id', 'orders', ['created_by_user_id'])
    _create_index_if_missing(bind, 'ix_orders_origin', 'orders', ['origin'])
    _create_index_if_missing(bind, 'ix_orders_confirmed_at', 'orders', ['confirmed_at'])

    if 'nif' in _columns(bind, 'users'):
        op.execute(sa.text("UPDATE users SET nif = NULL WHERE nif = ''"))
    op.execute(sa.text("UPDATE orders SET created_by_user_id = user_id WHERE created_by_user_id IS NULL"))
    op.execute(sa.text("UPDATE orders SET origin = 'client' WHERE origin IS NULL OR origin = ''"))
    op.execute(
        sa.text(
            """
            UPDATE orders
            SET confirmed_at = (
                SELECT MIN(h.changed_at)
                FROM order_status_history h
                WHERE h.order_id = orders.id AND h.new_status = 'confirmed'
            )
            WHERE confirmed_at IS NULL AND order_status IN ('confirmed', 'shipped')
            """
        )
    )

    _create_table_if_missing(
        bind,
        'admin_warning_ignores',
        [
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('warning_key', sa.String(length=191), nullable=False),
            sa.Column('warning_type', sa.String(length=80), nullable=False),
            sa.Column('entity_type', sa.String(length=80), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('ignored_by_user_id', sa.Integer(), nullable=True),
            sa.Column('ignored_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('reason', sa.Text(), nullable=True),
        ],
        [
            sa.UniqueConstraint('warning_key', name='uq_admin_warning_ignores_warning_key'),
            sa.UniqueConstraint('warning_type', 'entity_type', 'entity_id', 'warning_key', name='uq_admin_warning_ignores_identity'),
            sa.ForeignKeyConstraint(['ignored_by_user_id'], ['users.id'], name='fk_admin_warning_ignores_ignored_by_user_id_users', ondelete='SET NULL'),
        ],
    )

    _create_table_if_missing(
        bind,
        'admin_order_drafts',
        [
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('admin_user_id', sa.Integer(), nullable=False),
            sa.Column('customer_user_id', sa.Integer(), nullable=True),
            sa.Column('request_id', sa.String(length=80), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('draft_snapshot_json', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        ],
        [
            sa.UniqueConstraint('request_id', name='uq_admin_order_drafts_request_id'),
            sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], name='fk_admin_order_drafts_admin_user_id_users', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['customer_user_id'], ['users.id'], name='fk_admin_order_drafts_customer_user_id_users', ondelete='SET NULL'),
        ],
    )

    _create_table_if_missing(
        bind,
        'admin_order_draft_lines',
        [
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('draft_id', sa.Integer(), nullable=False),
            sa.Column('product_ref', sa.String(length=80), nullable=False),
            sa.Column('color', sa.String(length=80), nullable=False, server_default=''),
            sa.Column('size', sa.String(length=80), nullable=False, server_default=''),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('line_snapshot_json', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        ],
        [
            sa.UniqueConstraint('draft_id', 'product_ref', 'color', 'size', name='uq_admin_order_draft_lines_variant'),
            sa.ForeignKeyConstraint(['draft_id'], ['admin_order_drafts.id'], name='fk_admin_order_draft_lines_draft_id_admin_order_drafts', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['product_ref'], ['products.ref'], name='fk_admin_order_draft_lines_product_ref_products', ondelete='RESTRICT'),
        ],
    )

    _create_index_if_missing(bind, 'ix_admin_warning_ignores_warning_key', 'admin_warning_ignores', ['warning_key'])
    _create_index_if_missing(bind, 'ix_admin_warning_ignores_entity_id', 'admin_warning_ignores', ['entity_id'])
    _create_index_if_missing(bind, 'ix_admin_order_drafts_admin_user_id', 'admin_order_drafts', ['admin_user_id'])
    _create_index_if_missing(bind, 'ix_admin_order_drafts_customer_user_id', 'admin_order_drafts', ['customer_user_id'])
    _create_index_if_missing(bind, 'ix_admin_order_draft_lines_draft_id', 'admin_order_draft_lines', ['draft_id'])
    _create_index_if_missing(bind, 'ix_admin_order_draft_lines_product_ref', 'admin_order_draft_lines', ['product_ref'])


def downgrade() -> None:
    bind = op.get_bind()

    for index_name, table_name in [
        ('ix_admin_order_draft_lines_product_ref', 'admin_order_draft_lines'),
        ('ix_admin_order_draft_lines_draft_id', 'admin_order_draft_lines'),
        ('ix_admin_order_drafts_customer_user_id', 'admin_order_drafts'),
        ('ix_admin_order_drafts_admin_user_id', 'admin_order_drafts'),
        ('ix_admin_warning_ignores_entity_id', 'admin_warning_ignores'),
        ('ix_admin_warning_ignores_warning_key', 'admin_warning_ignores'),
        ('ix_orders_confirmed_at', 'orders'),
        ('ix_orders_origin', 'orders'),
        ('ix_orders_created_by_user_id', 'orders'),
    ]:
        if table_name in _tables(bind) and index_name in _indexes(bind, table_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in ['admin_order_draft_lines', 'admin_order_drafts', 'admin_warning_ignores']:
        if table_name in _tables(bind):
            op.drop_table(table_name)

    if 'orders' in _tables(bind):
        for column_name in ['confirmed_at', 'origin', 'created_by_user_id']:
            if column_name in _columns(bind, 'orders'):
                op.drop_column('orders', column_name)
    if 'users' in _tables(bind) and 'nif' in _columns(bind, 'users'):
        op.drop_column('users', 'nif')
