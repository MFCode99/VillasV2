from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Any


class DiagnosticsStore:
    def __init__(self, *, slow_request_ms: float = 1000.0) -> None:
        self.started_at = datetime.now(UTC)
        self.started_monotonic = monotonic()
        self.slow_request_ms = slow_request_ms
        self._lock = Lock()
        self._total_requests = 0
        self._error_requests = 0
        self._slow_requests = 0
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=20)
        self._recent_slow: deque[dict[str, Any]] = deque(maxlen=20)
        self._startup_checks: dict[str, Any] = {}

    def set_startup_checks(self, checks: dict[str, Any]) -> None:
        with self._lock:
            self._startup_checks = checks

    def record_request(self, *, method: str, path: str, status_code: int, duration_ms: float, request_id: str) -> None:
        row = {
            'time': datetime.now(UTC).isoformat(),
            'method': method,
            'path': path,
            'statusCode': status_code,
            'durationMs': round(duration_ms, 1),
            'requestId': request_id,
        }
        with self._lock:
            self._total_requests += 1
            if status_code >= 500:
                self._error_requests += 1
                self._recent_errors.appendleft(row)
            if duration_ms >= self.slow_request_ms:
                self._slow_requests += 1
                self._recent_slow.appendleft(row)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                'startedAt': self.started_at.isoformat(),
                'uptimeSeconds': round(monotonic() - self.started_monotonic),
                'totalRequests': self._total_requests,
                'errorRequests': self._error_requests,
                'slowRequests': self._slow_requests,
                'slowThresholdMs': self.slow_request_ms,
                'recentErrors': list(self._recent_errors),
                'recentSlowRequests': list(self._recent_slow),
                'startupChecks': dict(self._startup_checks),
            }


diagnostics = DiagnosticsStore()
