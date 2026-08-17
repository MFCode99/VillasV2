from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import LoginRateLimit


@dataclass(frozen=True)
class RateLimitKey:
    key: str


class LoginRateLimiter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _window_start(self, now: datetime) -> datetime:
        return now - timedelta(seconds=self.settings.login_rate_window_seconds)

    def _check_bucket(self, db: Session, bucket_key: str, limit: int) -> LoginRateLimit | None:
        now = self._now()
        row = db.get(LoginRateLimit, bucket_key)
        if row and row.blocked_until and row.blocked_until > now:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='too_many_attempts')
        if row and row.window_started_at < self._window_start(now):
            row.window_started_at = now
            row.failure_count = 0
            row.blocked_until = None
            db.flush()
        return row

    def allow(self, db: Session, ip_key: str, identifier_key: str) -> None:
        self._check_bucket(db, ip_key, self.settings.login_rate_ip_limit)
        self._check_bucket(db, identifier_key, self.settings.login_rate_identifier_limit)

    def register_failure(self, db: Session, ip_key: str, identifier_key: str) -> None:
        now = self._now()
        for bucket_key, limit in ((ip_key, self.settings.login_rate_ip_limit), (identifier_key, self.settings.login_rate_identifier_limit)):
            row = db.get(LoginRateLimit, bucket_key)
            if row is None:
                row = LoginRateLimit(bucket_key=bucket_key, window_started_at=now, failure_count=1)
                db.add(row)
                db.flush()
            else:
                if row.window_started_at < self._window_start(now):
                    row.window_started_at = now
                    row.failure_count = 0
                    row.blocked_until = None
                row.failure_count += 1
            if row.failure_count >= limit:
                row.blocked_until = now + timedelta(seconds=self.settings.login_rate_block_seconds)
        db.flush()

    def reset_identifier(self, db: Session, identifier_key: str) -> None:
        row = db.get(LoginRateLimit, identifier_key)
        if row:
            row.failure_count = 0
            row.blocked_until = None
            row.window_started_at = self._now()
            db.flush()
