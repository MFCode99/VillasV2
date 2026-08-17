from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from .models import User, UserRole


def current_user(request: Request) -> User | None:
    return getattr(request.state, 'current_user', None)


def require_authenticated_user(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, detail='login_required')
    return user


def require_admin(user: User = Depends(require_authenticated_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def require_developer(user: User = Depends(require_authenticated_user)) -> User:
    if user.role != UserRole.DEVELOPER.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def require_admin_or_developer(user: User = Depends(require_authenticated_user)) -> User:
    if user.role not in {UserRole.ADMIN.value, UserRole.DEVELOPER.value}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def require_client_or_above(user: User = Depends(require_authenticated_user)) -> User:
    return user


def require_client(user: User = Depends(require_authenticated_user)) -> User:
    if user.role != UserRole.CLIENT.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def require_user_owns(target_user_id: int, user: User = Depends(require_authenticated_user)) -> User:
    if user.role == UserRole.ADMIN.value or user.role == UserRole.DEVELOPER.value or user.id == target_user_id:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')


def require_roles(*roles: str):
    allowed = {role for role in roles}

    def _dependency(user: User = Depends(require_authenticated_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
        return user

    return _dependency
