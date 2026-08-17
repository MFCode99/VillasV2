from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import SessionLocal
from .models import Session as AppSession, User
from .security import hash_session_token, utcnow


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
    async def dispatch(self, request, call_next):
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

        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' https://unpkg.com; frame-ancestors 'none'")
        return response
