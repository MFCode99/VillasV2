"""initial villas v2 schema

Revision ID: 530402b178c0
Revises:
Create Date: 2026-08-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

from app.models import Base


revision = '530402b178c0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    pass
