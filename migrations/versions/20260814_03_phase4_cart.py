"""phase 4 server authoritative cart

Revision ID: 20260814_03
Revises: 20260814_02
Create Date: 2026-08-14 23:00:00.000000
"""

from __future__ import annotations

from alembic import op

from app.models import Base


revision = '20260814_03'
down_revision = '20260814_02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    pass
