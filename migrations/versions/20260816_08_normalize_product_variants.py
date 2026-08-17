"""Normalize imported product colors and sizes.

Revision ID: 20260816_08
Revises: 20260816_07
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = '20260816_08'
down_revision = '20260816_07'
branch_labels = None
depends_on = None


def _clean_token(value) -> str:
    text = str(value or '').strip()
    text = text.strip('[](){}').strip().strip('"').strip("'").strip()
    text = text.strip('[](){}').strip().strip('"').strip("'").strip()
    return text


def _normalize(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        try:
            decoded = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            decoded = None
        raw_items = decoded if isinstance(decoded, list) else text.split(',')
    elif isinstance(value, Iterable):
        raw_items = []
        for item in value:
            if isinstance(item, str) and ',' in item:
                raw_items.extend(item.split(','))
            else:
                raw_items.append(item)
    else:
        raw_items = [value]
    result: list[str] = []
    for raw in raw_items:
        cleaned = _clean_token(raw)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def upgrade() -> None:
    bind = op.get_bind()
    products = sa.table(
        'products',
        sa.column('ref', sa.String(length=80)),
        sa.column('colors_json', sa.JSON()),
        sa.column('sizes_json', sa.JSON()),
    )
    rows = bind.execute(sa.select(products.c.ref, products.c.colors_json, products.c.sizes_json)).mappings()
    for row in rows:
        colors = _normalize(row['colors_json'])
        sizes = _normalize(row['sizes_json'])
        if colors != (row['colors_json'] or []) or sizes != (row['sizes_json'] or []):
            bind.execute(
                products.update().where(products.c.ref == row['ref']).values(colors_json=colors, sizes_json=sizes)
            )


def downgrade() -> None:
    # The previous punctuation was import corruption and cannot be meaningfully restored.
    pass
