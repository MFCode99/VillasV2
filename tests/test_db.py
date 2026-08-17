from __future__ import annotations

from sqlalchemy import text

from app.db import TestEngine


def test_test_database_connection():
    with TestEngine.connect() as conn:
        value = conn.execute(text('SELECT 1')).scalar_one()
        assert value == 1