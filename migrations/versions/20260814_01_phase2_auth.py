"""phase 2 auth and authorization foundation

Revision ID: 20260814_01
Revises: 530402b178c0
Create Date: 2026-08-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import Base


revision = '20260814_01'
down_revision = '530402b178c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)

    def add_column_if_missing(table_name: str, column: sa.Column) -> None:
        existing = {col['name'] for col in inspector.get_columns(table_name)}
        if column.name not in existing:
            op.add_column(table_name, column)

    add_column_if_missing('users', sa.Column('company_name', sa.String(length=150), nullable=True))
    add_column_if_missing('users', sa.Column('phone', sa.String(length=30), nullable=True))
    add_column_if_missing('users', sa.Column('address_line1', sa.String(length=150), nullable=True))
    add_column_if_missing('users', sa.Column('address_line2', sa.String(length=150), nullable=True))
    add_column_if_missing('users', sa.Column('postal_code', sa.String(length=20), nullable=True))
    add_column_if_missing('users', sa.Column('city', sa.String(length=120), nullable=True))
    add_column_if_missing('users', sa.Column('country', sa.String(length=120), nullable=True))

    add_column_if_missing('sessions', sa.Column('auth_context_json', sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE sessions SET auth_context_json = JSON_OBJECT() WHERE auth_context_json IS NULL"))

    add_column_if_missing('login_logs', sa.Column('username_input', sa.String(length=80), nullable=False, server_default=''))
    add_column_if_missing('login_logs', sa.Column('failure_reason', sa.String(length=80), nullable=True))
    add_column_if_missing('login_logs', sa.Column('request_id', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE login_logs DROP COLUMN IF EXISTS request_id"))
    op.execute(sa.text("ALTER TABLE login_logs DROP COLUMN IF EXISTS failure_reason"))
    op.execute(sa.text("ALTER TABLE login_logs DROP COLUMN IF EXISTS username_input"))
    op.execute(sa.text("ALTER TABLE sessions DROP COLUMN IF EXISTS auth_context_json"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS country"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS city"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS postal_code"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS address_line2"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS address_line1"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS phone"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS company_name"))
