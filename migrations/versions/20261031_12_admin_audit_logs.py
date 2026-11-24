"""Add the administrative activity log.

Revision ID: 20261031_12
Revises: 20261029_11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20261031_12'
down_revision = '20261029_11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if 'admin_audit_logs' in inspect(bind).get_table_names():
        return
    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('actor_username', sa.String(length=80), nullable=False),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('entity_type', sa.String(length=80), nullable=False),
        sa.Column('entity_id', sa.String(length=191), nullable=True),
        sa.Column('route', sa.String(length=255), nullable=False),
        sa.Column('request_id', sa.String(length=80), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_admin_audit_logs_actor_user_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit_logs')),
    )
    for column in ('actor_user_id', 'actor_username', 'action', 'entity_type', 'entity_id', 'request_id', 'created_at'):
        op.create_index(op.f(f'ix_admin_audit_logs_{column}'), 'admin_audit_logs', [column], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if 'admin_audit_logs' in inspect(bind).get_table_names():
        op.drop_table('admin_audit_logs')
