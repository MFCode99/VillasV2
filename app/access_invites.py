from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Session as AppSession, User, UserAccessInvite
from .security import hash_password, utcnow


INVITE_DEFAULT_HOURS = 1
INVITE_MAX_HOURS = 24 * 30


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_access_invite(
    db: Session,
    *,
    user_id: int,
    created_by_user_id: int,
    expires_in_hours: int = INVITE_DEFAULT_HOURS,
) -> tuple[User, UserAccessInvite, str]:
    if not 1 <= expires_in_hours <= INVITE_MAX_HOURS:
        raise HTTPException(status_code=400, detail='invite_duration_invalid')
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    if not user.active:
        raise HTTPException(status_code=400, detail='user_not_available')
    now = utcnow()
    for invite in db.execute(
        select(UserAccessInvite).where(
            UserAccessInvite.user_id == user_id,
            UserAccessInvite.used_at.is_(None),
            UserAccessInvite.expires_at > now,
        )
    ).scalars():
        invite.expires_at = now
    token = secrets.token_urlsafe(32)
    invite = UserAccessInvite(
        user_id=user_id,
        created_by_user_id=created_by_user_id,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(hours=expires_in_hours),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return user, invite, token


def get_access_invite(db: Session, token: str, *, lock: bool = False) -> tuple[UserAccessInvite, User]:
    if not token or len(token) > 256:
        raise HTTPException(status_code=404, detail='invite_invalid')
    query = select(UserAccessInvite).where(UserAccessInvite.token_hash == _token_hash(token))
    if lock:
        query = query.with_for_update()
    invite = db.execute(query).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail='invite_invalid')
    if invite.used_at is not None:
        raise HTTPException(status_code=410, detail='invite_used')
    if invite.expires_at <= utcnow():
        raise HTTPException(status_code=410, detail='invite_expired')
    user = db.get(User, invite.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=410, detail='user_not_available')
    return invite, user


def accept_access_invite(db: Session, *, token: str, password: str) -> User:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail='password_too_short')
    invite, user = get_access_invite(db, token, lock=True)
    now = utcnow()
    user.password_hash = hash_password(password)
    invite.used_at = now
    sessions = db.execute(
        select(AppSession).where(AppSession.user_id == user.id, AppSession.revoked_at.is_(None))
    ).scalars().all()
    for session in sessions:
        session.revoked_at = now
    db.commit()
    db.refresh(user)
    return user
