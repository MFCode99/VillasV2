#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.catalog import validate_catalog_migration


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_file(ROOT / '.env')
    from app.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description='Validate Villas V1 -> V2 catalog migration')
    parser.add_argument('--source', default=None, help='Source database URL for Villas V1')
    parser.add_argument('--target', choices=['test', 'production'], default='test', help='Destination database')
    parser.add_argument('--media-root', default=str(ROOT / 'media'), help='Destination media root')
    args = parser.parse_args()

    source_url = args.source or os.environ.get('V1_DATABASE_URL') or os.environ.get('SOURCE_DATABASE_URL') or os.environ.get('MYSQL_SOURCE_URL')
    if not source_url:
        host = os.environ.get('VILLAS_DB_HOST', 'localhost')
        user = os.environ.get('VILLAS_DB_USER', 'villas_user')
        password = os.environ.get('VILLAS_DB_PASS', 'Villas@2026!')
        database = os.environ.get('VILLAS_DB_NAME', 'villas')
        source_url = URL.create(
            drivername='mysql+pymysql',
            username=user,
            password=password,
            host=host,
            database=database,
            query={'charset': 'utf8mb4'},
        ).render_as_string(hide_password=False)
    target_url = settings.database_url_test if args.target == 'test' else settings.database_url
    if not target_url:
        raise SystemExit('Missing DATABASE_URL/DATABASE_URL_TEST for target environment.')
    media_root = Path(args.media_root)

    target_engine = create_engine(target_url, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(bind=target_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    with SessionLocal() as db:
        validation = validate_catalog_migration(source_url=source_url, target_db=db, media_root=media_root)
        print(json.dumps(
            {
                'source_products': validation.source_products,
                'target_products': validation.target_products,
                'source_categories': validation.source_categories,
                'target_categories': validation.target_categories,
                'matched_products': validation.matched_products,
                'matched_images': validation.matched_images,
                'passed': validation.passed,
                'issues': [
                    {
                        'ref': issue.ref,
                        'field': issue.field,
                        'expected': issue.expected,
                        'actual': issue.actual,
                        'severity': issue.severity,
                    }
                    for issue in validation.issues[:100]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0 if validation.passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
