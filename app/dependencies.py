from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import SessionLocal
from .authz import require_authenticated_user
from .models import User


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request) -> User | None:
    return getattr(request.state, 'current_user', None)


def require_user(user: User = Depends(get_current_user)) -> User:
    return require_authenticated_user(user)
