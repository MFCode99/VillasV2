from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .diagnostics import diagnostics
from .db import SessionLocal
from .models import AdminAuditLog, Session as AppSession, User
from .security import hash_session_token, utcnow

logger = logging.getLogger(__name__)


def _cache_control_for_path(path: str) -> str:
    if path.startswith(('/assets/', '/media/')):
        return 'public, max-age=31536000, immutable'
    if path.startswith('/icons/'):
        return 'public, max-age=2592000, immutable'
    if path.startswith('/static/'):
        return 'public, max-age=604800, stale-while-revalidate=86400'
    if path == '/manifest.webmanifest':
        return 'public, max-age=300, must-revalidate'
    return 'no-store'


def _parse_proxy_list(raw: str) -> set[str]:
    items = [item.strip() for item in raw.split(',') if item.strip()]
    return set(items)


def _client_ip_from_request(request) -> str | None:
    settings = get_settings()
    remote_addr = request.client.host if request.client else None
    trusted = _parse_proxy_list(settings.trusted_proxy_values)
    if remote_addr and remote_addr in trusted:
        xff = request.headers.get('x-forwarded-for', '')
        if xff:
            return xff.split(',')[0].strip()
        x_real = request.headers.get('x-real-ip')
        if x_real:
            return x_real.strip()
    return remote_addr


class RequestContextMiddleware(BaseHTTPMiddleware):
    @staticmethod
    def _audit_target(request) -> tuple[str, str | None]:
        parts = [part for part in request.url.path.split('/') if part]
        if parts[:2] == ['api', 'v1']:
            parts = parts[2:]
        if parts and parts[0] == 'admin':
            parts = parts[1:]
        entity_type = parts[0] if parts else 'admin'
        entity_id = next((part for part in parts[1:] if part not in {'active', 'status', 'notes', 'image', 'save', 'catalogs', 'password', 'preview', 'commit'}), None)
        return entity_type[:80], entity_id[:191] if entity_id else None

    @staticmethod
    def _record_admin_action(request, response, user) -> None:
        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'} or response.status_code >= 400:
            return
        if user is None or getattr(user, 'role', None) not in {'admin', 'developer'}:
            return
        entity_type, entity_id = RequestContextMiddleware._audit_target(request)
        route = getattr(request.scope.get('route'), 'path', request.url.path)
        db = SessionLocal()
        try:
            db.add(AdminAuditLog(
                actor_user_id=user.id,
                actor_username=user.username,
                action=request.method.lower(),
                entity_type=entity_type,
                entity_id=entity_id,
                route=str(route)[:255],
                request_id=getattr(request.state, 'request_id', None),
                ip_address=getattr(request.state, 'client_ip', None),
                user_agent=(request.headers.get('user-agent') or '')[:255] or None,
                status_code=response.status_code,
                metadata_json={},
            ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def dispatch(self, request, call_next):
        started_at = perf_counter()
        settings = get_settings()
        request_id = request.headers.get('X-Request-ID') or uuid4().hex
        request.state.request_id = request_id
        request.state.client_ip = _client_ip_from_request(request)
        request.state.current_user = None
        request.state.current_session = None

        session_token = request.cookies.get(settings.session_cookie_name)
        if session_token:
            session_hash = hash_session_token(session_token, settings.session_secret)
            db = SessionLocal()
            try:
                session = db.get(AppSession, session_hash)
                now = utcnow()
                if session and not session.revoked_at and session.expires_at > now:
                    user = db.get(User, session.user_id)
                    if user and user.active:
                        request.state.current_session = session
                        request.state.current_user = user
                        if session.last_seen_at is None or (now - session.last_seen_at).total_seconds() > 60:
                            session.last_seen_at = now
                            db.commit()
                elif session and session.expires_at <= now and not session.revoked_at:
                    session.revoked_at = now
                    db.commit()
            finally:
                db.close()

        audit_user = request.state.current_user
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            diagnostics.record_request(method=request.method, path=request.url.path, status_code=500, duration_ms=duration_ms, request_id=request_id)
            logger.exception('request_failed method=%s path=%s duration_ms=%.1f', request.method, request.url.path, duration_ms, extra={'request_id': request_id})
            raise
        duration_ms = (perf_counter() - started_at) * 1000
        diagnostics.record_request(method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms, request_id=request_id)
        if duration_ms >= diagnostics.slow_request_ms:
            logger.warning('slow_request method=%s path=%s status=%s duration_ms=%.1f', request.method, request.url.path, response.status_code, duration_ms, extra={'request_id': request_id})
        self._record_admin_action(request, response, audit_user)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Response-Time-Ms'] = f'{duration_ms:.1f}'
        response.headers['Server-Timing'] = f'app;dur={duration_ms:.1f}'
        response.headers['Cache-Control'] = _cache_control_for_path(request.url.path)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' https://unpkg.com; frame-ancestors 'none'")
        return response
