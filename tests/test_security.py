from __future__ import annotations

from app.security import hash_password, verify_password, new_session_id, new_csrf_token, hash_csrf_token


def test_password_hash_roundtrip():
    hashed = hash_password('secret123')
    assert verify_password(hashed, 'secret123') is True
    assert verify_password(hashed, 'wrong') is False


def test_tokens_and_csrf():
    sid = new_session_id()
    token = new_csrf_token()
    assert len(sid) >= 20
    assert len(token) >= 20
    digest = hash_csrf_token(token, 'salt')
    assert len(digest) == 64