from __future__ import annotations

from app.security import has_any_role


def test_role_checks():
    assert has_any_role('admin', ['admin', 'developer'])
    assert not has_any_role('client', ['admin'])