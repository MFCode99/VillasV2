"""phase 5 orders lifecycle, emails and pdf support

Revision ID: 20260814_04
Revises: 20260814_03
Create Date: 2026-08-14 23:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260814_04'
down_revision = '20260814_03'
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {col['name'] for col in inspect(bind).get_columns(table_name)}


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def _index_names(bind, table_name: str) -> set[str]:
    return {idx['name'] for idx in inspect(bind).get_indexes(table_name)}


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name not in _index_names(bind, table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()

    _add_column_if_missing(bind, 'orders', sa.Column('customer_email', sa.String(length=150), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_phone', sa.String(length=30), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_company', sa.String(length=150), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_address_line1', sa.String(length=150), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_address_line2', sa.String(length=150), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_postal_code', sa.String(length=20), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_city', sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_country', sa.String(length=120), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('customer_snapshot_json', sa.JSON(), nullable=True))
    _add_column_if_missing(bind, 'orders', sa.Column('snapshot_json', sa.JSON(), nullable=True))

    _add_column_if_missing(bind, 'order_status_history', sa.Column('request_id', sa.String(length=80), nullable=True))
    _add_column_if_missing(bind, 'order_status_history', sa.Column('changed_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))

    _add_column_if_missing(bind, 'order_request_ids', sa.Column('request_hash', sa.String(length=64), nullable=True))

    _add_column_if_missing(bind, 'email_delivery_logs', sa.Column('request_id', sa.String(length=80), nullable=True))
    _add_column_if_missing(bind, 'email_delivery_logs', sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'))

    op.execute(sa.text("UPDATE orders SET order_status='pending' WHERE order_status IN ('created', '') OR order_status IS NULL"))
    op.execute(sa.text("UPDATE orders SET email_status='pending' WHERE email_status IS NULL OR email_status=''"))
    op.execute(sa.text("UPDATE orders SET customer_snapshot_json = JSON_OBJECT() WHERE customer_snapshot_json IS NULL"))
    op.execute(sa.text("UPDATE orders SET snapshot_json = JSON_OBJECT() WHERE snapshot_json IS NULL"))
    op.execute(sa.text("UPDATE order_status_history SET changed_at = created_at WHERE changed_at IS NULL"))
    op.execute(sa.text("UPDATE email_delivery_logs SET attempt = 1 WHERE attempt IS NULL"))

    _create_index_if_missing(bind, 'ix_orders_request_id', 'orders', ['request_id'], unique=True)
    _create_index_if_missing(bind, 'ix_orders_public_number', 'orders', ['public_number'], unique=True)
    _create_index_if_missing(bind, 'ix_order_status_history_request_id', 'order_status_history', ['request_id'])
    _create_index_if_missing(bind, 'ix_email_delivery_logs_request_id', 'email_delivery_logs', ['request_id'])


def downgrade() -> None:
    bind = op.get_bind()

    for index_name, table_name in [
        ('ix_email_delivery_logs_request_id', 'email_delivery_logs'),
        ('ix_order_status_history_request_id', 'order_status_history'),
        ('ix_orders_public_number', 'orders'),
        ('ix_orders_request_id', 'orders'),
    ]:
        if index_name in _index_names(bind, table_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name, column_name in [
        ('email_delivery_logs', 'attempt'),
        ('email_delivery_logs', 'request_id'),
        ('order_request_ids', 'request_hash'),
        ('order_status_history', 'changed_at'),
        ('order_status_history', 'request_id'),
        ('orders', 'snapshot_json'),
        ('orders', 'customer_snapshot_json'),
        ('orders', 'customer_country'),
        ('orders', 'customer_city'),
        ('orders', 'customer_postal_code'),
        ('orders', 'customer_address_line2'),
        ('orders', 'customer_address_line1'),
        ('orders', 'customer_company'),
        ('orders', 'customer_phone'),
        ('orders', 'customer_email'),
    ]:
        if column_name in _columns(bind, table_name):
            op.drop_column(table_name, column_name)
