from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=2, hash_len=32, salt_len=16)


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(hash_value: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(hash_value, password)
    except VerifyMismatchError:
        return False


def needs_rehash(hash_value: str) -> bool:
    return _PASSWORD_HASHER.check_needs_rehash(hash_value)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, secret: str) -> str:
    payload = f'{token}:{secret}'.encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def hash_csrf_token(token: str, secret: str) -> str:
    payload = f'{token}:{secret}'.encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def verify_csrf_token(token: str, secret: str, expected_hash: str) -> bool:
    return constant_time_equals(hash_csrf_token(token, secret), expected_hash)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def has_any_role(user_role: str | None, allowed: Iterable[str]) -> bool:
    return bool(user_role and user_role in set(allowed))


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def normalize_login_identifier(value: str) -> str:
    return normalize_username(value)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def public_order_number(year: int, sequence: int) -> str:
    return f'VLS-{year}-{sequence:06d}'
