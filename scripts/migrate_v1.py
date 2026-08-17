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

from app.catalog import import_v1_catalog
from app.config import get_settings


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_target_url(target: str) -> str:
    settings = get_settings()
    if target == 'production':
        value = settings.database_url
    else:
        value = settings.database_url_test or settings.database_url
    if not value:
        raise SystemExit('Missing DATABASE_URL/DATABASE_URL_TEST for target environment.')
    return value


def resolve_source_url() -> str:
    for key in ('V1_DATABASE_URL', 'SOURCE_DATABASE_URL', 'MYSQL_SOURCE_URL'):
        value = os.environ.get(key)
        if value:
            return value

    host = os.environ.get('VILLAS_DB_HOST', 'localhost')
    user = os.environ.get('VILLAS_DB_USER', 'villas_user')
    password = os.environ.get('VILLAS_DB_PASS', 'Villas@2026!')
    database = os.environ.get('VILLAS_DB_NAME', 'villas')
    return URL.create(
        drivername='mysql+pymysql',
        username=user,
        password=password,
        host=host,
        database=database,
        query={'charset': 'utf8mb4'},
    ).render_as_string(hide_password=False)


def main() -> int:
    load_env_file(ROOT / '.env')
    parser = argparse.ArgumentParser(description='Villas V1 -> V2 catalog migrator')
    parser.add_argument('--source', default=None, help='Source database URL for Villas V1')
    parser.add_argument('--target', choices=['test', 'production'], default='test', help='Destination database')
    parser.add_argument('--apply', action='store_true', help='Write data instead of dry-run')
    parser.add_argument('--validate-after', action='store_true', help='Run validation after migration')
    parser.add_argument('--media-root', default=str(ROOT / 'media'), help='Destination media root')
    args = parser.parse_args()

    source_url = args.source or resolve_source_url()
    target_url = resolve_target_url(args.target)
    media_root = Path(args.media_root)
    media_root.mkdir(parents=True, exist_ok=True)

    target_engine = create_engine(target_url, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(bind=target_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    print(f'SOURCE DB: {source_url.rsplit("/", 1)[-1]}')
    print(f'TARGET DB: {target_url.rsplit("/", 1)[-1]}')
    print(f'MODE: {"apply" if args.apply else "dry-run"}')

    with SessionLocal() as db:
        summary = import_v1_catalog(db, source_url=source_url, media_root=media_root, dry_run=not args.apply)
        print(json.dumps(
            {
                'categories_seen': summary.categories_seen,
                'products_seen': summary.products_seen,
                'categories_created': summary.categories_created,
                'categories_updated': summary.categories_updated,
                'products_created': summary.products_created,
                'products_updated': summary.products_updated,
                'images_written': summary.images_written,
                'dry_run': summary.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        ))
        if args.validate_after:
            from app.catalog import validate_catalog_migration

            validation = validate_catalog_migration(source_url=source_url, target_db=db, media_root=media_root)
            print(json.dumps(
                {
                    'source_products': validation.source_products,
                    'target_products': validation.target_products,
                    'source_categories': validation.source_categories,
                    'target_categories': validation.target_categories,
                    'matched_products': validation.matched_products,
                    'matched_images': validation.matched_images,
                    'issues': [
                        {
                            'ref': issue.ref,
                            'field': issue.field,
                            'expected': issue.expected,
                            'actual': issue.actual,
                            'severity': issue.severity,
                        }
                        for issue in validation.issues[:50]
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ))
            if not validation.passed:
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
