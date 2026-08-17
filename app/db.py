from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from .models import Base

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=10,
    future=True,
)

TestEngine = create_engine(
    settings.database_url_test,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=2,
    max_overflow=5,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
TestSessionLocal = sessionmaker(bind=TestEngine, autoflush=False, autocommit=False, expire_on_commit=False)