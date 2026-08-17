from __future__ import annotations

import os
import socket
import tempfile
from uuid import uuid4
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
env_file = ROOT / '.env'
if env_file.exists():
    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

database_url_test = os.environ.get('DATABASE_URL_TEST')
if database_url_test:
    try:
        parsed = make_url(database_url_test)
        if parsed.get_backend_name().startswith('mysql'):
            host = parsed.host or '127.0.0.1'
            port = parsed.port or 3306
            with socket.create_connection((host, port), timeout=0.2):
                pass
        os.environ['DATABASE_URL'] = database_url_test
    except OSError:
        sqlite_path = Path(tempfile.gettempdir()) / f'villas-v2-test-{uuid4().hex}.sqlite3'
        sqlite_url = f'sqlite:///{sqlite_path.as_posix()}'
        os.environ['DATABASE_URL'] = sqlite_url
        os.environ['DATABASE_URL_TEST'] = sqlite_url
os.environ.setdefault('APP_ENV', 'test')

from app.main import app
from app.db import TestEngine
from app.models import Base


@pytest.fixture(scope='session', autouse=True)
def ensure_test_schema():
    Base.metadata.create_all(bind=TestEngine, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def clear_test_data():
    with TestEngine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture()
def client():
    return TestClient(app)
