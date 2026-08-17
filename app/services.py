from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import desc, func, or_, select, update as sql_update
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import DeveloperNote, LoginLog, Order, OrderStatusHistory, Session as AppSession, SiteSetting, User, UserRole
from .rate_limit import LoginRateLimiter
from .security import hash_csrf_token, hash_password, hash_session_token, needs_rehash, new_csrf_token, new_session_id, normalize_login_identifier, utcnow, verify_csrf_token, verify_password


def landing_path_for_role(role: str) -> str:
    if role == UserRole.ADMIN.value:
        return '/admin'
    if role == UserRole.DEVELOPER.value:
        return '/developer'
    return '/catalogo'


def _coerce_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _normalize_role(role: str | None) -> str:
    if not role:
        return UserRole.CLIENT.value
    normalized = role.strip().casefold()
    if normalized not in {item.value for item in UserRole}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_role')
    return normalized


@dataclass(frozen=True)
class DashboardStats:
    total_users: int
    total_clients: int
    total_admins: int
    total_developers: int
    active_sessions: int
    recent_login_attempts: int


class HealthService:
    def __init__(self, db: Session):
        self.db = db

    def check_database(self) -> None:
        self.db.execute(select(1)).scalar_one()


class AuthService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.rate_limiter = LoginRateLimiter(self.settings)

    def _ip_key(self, ip: str | None) -> str:
        return f'ip:{ip or "unknown"}'

    def _identifier_key(self, username: str) -> str:
        return f'user:{normalize_login_identifier(username)}'

    def _log_login_attempt(
        self,
        db: Session,
        *,
        username_input: str,
        success: bool,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
        failure_reason: str | None = None,
        user_id: int | None = None,
    ) -> None:
        db.add(
            LoginLog(
                user_id=user_id,
                username_input=username_input,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason,
                request_id=request_id,
            )
        )

    def authenticate(
        self,
        db: Session,
        *,
        username: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> User | None:
        identifier = normalize_login_identifier(username)
        ip_key = self._ip_key(ip)
        identifier_key = self._identifier_key(identifier)
        try:
            self.rate_limiter.allow(db, ip_key, identifier_key)
        except HTTPException:
            self._log_login_attempt(
                db,
                username_input=username.strip(),
                success=False,
                ip_address=ip,
                user_agent=user_agent,
                request_id=request_id,
                failure_reason='rate_limited',
            )
            db.commit()
            raise

        user = db.scalar(select(User).where(User.username == identifier))
        if user is None:
            self.rate_limiter.register_failure(db, ip_key, identifier_key)
            self._log_login_attempt(
                db,
                username_input=username.strip(),
                success=False,
                ip_address=ip,
                user_agent=user_agent,
                request_id=request_id,
                failure_reason='invalid_credentials',
            )
            db.commit()
            return None

        if not user.active:
            self.rate_limiter.register_failure(db, ip_key, identifier_key)
            self._log_login_attempt(
                db,
                username_input=username.strip(),
                success=False,
                ip_address=ip,
                user_agent=user_agent,
                request_id=request_id,
                failure_reason='inactive',
                user_id=user.id,
            )
            db.commit()
            return None

        if not verify_password(user.password_hash, password):
            self.rate_limiter.register_failure(db, ip_key, identifier_key)
            self._log_login_attempt(
                db,
                username_input=username.strip(),
                success=False,
                ip_address=ip,
                user_agent=user_agent,
                request_id=request_id,
                failure_reason='invalid_credentials',
                user_id=user.id,
            )
            db.commit()
            return None

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        return user

    def create_session(
        self,
        db: Session,
        user: User,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        session_token = new_session_id()
        csrf_token = new_csrf_token()
        now = utcnow()
        expires_at = now + timedelta(minutes=self.settings.session_ttl_minutes)
        db.add(
            AppSession(
                session_token_hash=hash_session_token(session_token, self.settings.session_secret),
                user_id=user.id,
                csrf_token_hash=hash_csrf_token(csrf_token, self.settings.csrf_secret),
                ip_address=ip,
                user_agent=user_agent,
                expires_at=expires_at,
                auth_context_json=auth_context or {},
            )
        )
        user.last_login_at = now
        self.rate_limiter.reset_identifier(db, self._identifier_key(user.username))
        self._log_login_attempt(
            db,
            username_input=user.username,
            success=True,
            ip_address=ip,
            user_agent=user_agent,
            request_id=request_id,
            user_id=user.id,
        )
        db.commit()
        return session_token, csrf_token

    def validate_csrf_submission(self, request: Request, submitted_token: str | None) -> None:
        if not submitted_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='csrf_missing')
        session = getattr(request.state, 'current_session', None)
        if session is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='csrf_invalid')
        if not verify_csrf_token(submitted_token, self.settings.csrf_secret, session.csrf_token_hash):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='csrf_invalid')

    def revoke_session(self, db: Session, session_token: str | None) -> None:
        if not session_token:
            return
        session_hash = hash_session_token(session_token, self.settings.session_secret)
        session = db.get(AppSession, session_hash)
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            db.commit()

    def revoke_user_sessions(self, db: Session, user_id: int) -> int:
        now = utcnow()
        rows = db.execute(
            select(AppSession).where(AppSession.user_id == user_id, AppSession.revoked_at.is_(None))
        ).scalars().all()
        for session in rows:
            session.revoked_at = now
        db.commit()
        return len(rows)


class UserAdminService:
    def list_users(
        self,
        db: Session,
        limit: int = 200,
        *,
        q: str | None = None,
        role: str | None = None,
        active: bool | None = None,
    ) -> list[User]:
        stmt = select(User)
        if q:
            pattern = f'%{q.strip()}%'
            stmt = stmt.where(
                or_(
                    User.username.like(pattern),
                    User.full_name.like(pattern),
                    User.company_name.like(pattern),
                    User.email.like(pattern),
                    User.nif.like(pattern),
                    User.phone.like(pattern),
                )
            )
        if role:
            stmt = stmt.where(User.role == role)
        if active is not None:
            stmt = stmt.where(User.active.is_(active))
        stmt = stmt.order_by(desc(User.created_at), desc(User.id)).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def get_user(self, db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    def create_user(
        self,
        db: Session,
        *,
        username: str,
        password: str,
        full_name: str,
        role: str = UserRole.CLIENT.value,
        email: str | None = None,
        nif: str | None = None,
        company_name: str | None = None,
        phone: str | None = None,
        address_line1: str | None = None,
        address_line2: str | None = None,
        postal_code: str | None = None,
        city: str | None = None,
        country: str | None = None,
        active: bool = True,
        metadata_json: dict[str, Any] | None = None,
    ) -> User:
        username_value = normalize_login_identifier(username)
        if not username_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='username_required')
        if not full_name.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='full_name_required')
        if not password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='password_required')
        if db.scalar(select(User.id).where(User.username == username_value)) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='username_exists')
        user = User(
            username=username_value,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=_normalize_role(role),
            email=_coerce_optional_text(email),
            nif=_coerce_optional_text(nif),
            company_name=_coerce_optional_text(company_name),
            phone=_coerce_optional_text(phone),
            address_line1=_coerce_optional_text(address_line1),
            address_line2=_coerce_optional_text(address_line2),
            postal_code=_coerce_optional_text(postal_code),
            city=_coerce_optional_text(city),
            country=_coerce_optional_text(country),
            active=_coerce_bool(active),
            metadata_json=metadata_json or {},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def update_user(
        self,
        db: Session,
        user_id: int,
        *,
        full_name: str | None = None,
        email: str | None = None,
        nif: str | None = None,
        company_name: str | None = None,
        phone: str | None = None,
        address_line1: str | None = None,
        address_line2: str | None = None,
        postal_code: str | None = None,
        city: str | None = None,
        country: str | None = None,
        role: str | None = None,
        active: bool | None = None,
        admin_notes: str | None = None,
    ) -> User:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
        if full_name is not None:
            user.full_name = full_name.strip()
        if email is not None:
            user.email = _coerce_optional_text(email)
        if nif is not None:
            user.nif = _coerce_optional_text(nif)
        if company_name is not None:
            user.company_name = _coerce_optional_text(company_name)
        if phone is not None:
            user.phone = _coerce_optional_text(phone)
        if address_line1 is not None:
            user.address_line1 = _coerce_optional_text(address_line1)
        if address_line2 is not None:
            user.address_line2 = _coerce_optional_text(address_line2)
        if postal_code is not None:
            user.postal_code = _coerce_optional_text(postal_code)
        if city is not None:
            user.city = _coerce_optional_text(city)
        if country is not None:
            user.country = _coerce_optional_text(country)
        if role is not None:
            user.role = _normalize_role(role)
        if active is not None:
            user.active = _coerce_bool(active)
        if admin_notes is not None:
            user.admin_notes = _coerce_optional_text(admin_notes)
        db.commit()
        db.refresh(user)
        return user

    def set_active(self, db: Session, user_id: int, active: bool) -> User:
        return self.update_user(db, user_id, active=active)

    def set_role(self, db: Session, user_id: int, role: str) -> User:
        return self.update_user(db, user_id, role=role)

    def reset_password(self, db: Session, user_id: int, password: str) -> User:
        if len(password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='password_too_short')
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
        user.password_hash = hash_password(password)
        db.commit()
        db.refresh(user)
        return user

    def delete_user(self, db: Session, user_id: int) -> bool:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
        has_orders = db.scalar(
            select(Order.id).where(or_(Order.user_id == user_id, Order.created_by_user_id == user_id)).limit(1)
        )
        has_order_history = db.scalar(
            select(OrderStatusHistory.id).where(OrderStatusHistory.changed_by_user_id == user_id).limit(1)
        )
        if has_orders is not None or has_order_history is not None:
            return False
        db.delete(user)
        db.commit()
        return True

    def set_all_clients_active(self, db: Session, active: bool) -> int:
        result = db.execute(
            sql_update(User).where(User.role == UserRole.CLIENT.value).values(active=_coerce_bool(active))
        )
        db.commit()
        return int(result.rowcount or 0)


class DeveloperService:
    def dashboard_stats(self, db: Session) -> DashboardStats:
        total_users = db.scalar(select(func.count(User.id))) or 0
        total_clients = db.scalar(select(func.count(User.id)).where(User.role == UserRole.CLIENT.value)) or 0
        total_admins = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN.value)) or 0
        total_developers = db.scalar(select(func.count(User.id)).where(User.role == UserRole.DEVELOPER.value)) or 0
        active_sessions = db.scalar(select(func.count(AppSession.session_token_hash)).where(AppSession.revoked_at.is_(None), AppSession.expires_at > utcnow())) or 0
        recent_login_attempts = db.scalar(select(func.count(LoginLog.id)).where(LoginLog.created_at >= utcnow() - timedelta(days=1))) or 0
        return DashboardStats(
            total_users=total_users,
            total_clients=total_clients,
            total_admins=total_admins,
            total_developers=total_developers,
            active_sessions=active_sessions,
            recent_login_attempts=recent_login_attempts,
        )

    def login_logs(self, db: Session, limit: int = 50) -> list[LoginLog]:
        stmt = select(LoginLog).order_by(desc(LoginLog.created_at), desc(LoginLog.id)).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def recent_sessions(self, db: Session, limit: int = 50) -> list[AppSession]:
        stmt = select(AppSession).order_by(desc(AppSession.created_at), desc(AppSession.last_seen_at)).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def settings(self, db: Session) -> list[SiteSetting]:
        stmt = select(SiteSetting).order_by(SiteSetting.key.asc())
        return list(db.execute(stmt).scalars().all())

    def notes(self, db: Session, limit: int = 20) -> list[DeveloperNote]:
        stmt = select(DeveloperNote).order_by(desc(DeveloperNote.created_at), desc(DeveloperNote.id)).limit(limit)
        return list(db.execute(stmt).scalars().all())
