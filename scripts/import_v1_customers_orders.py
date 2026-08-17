#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Order, OrderLine, OrderRequestId, Product, User
from app.security import hash_password
from app.security import public_order_number


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def resolve_target_url(target: str) -> str:
    settings = get_settings()
    if target == 'production':
        value = settings.database_url
    else:
        value = settings.database_url_test or settings.database_url
    if not value:
        raise SystemExit('Missing DATABASE_URL/DATABASE_URL_TEST for target environment.')
    return value


def normalize_text(value: Any) -> str:
    return (str(value).strip() if value is not None else '').strip()


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal:
    if value in (None, ''):
        if default is None:
            return Decimal('0.00')
        return default
    if isinstance(value, Decimal):
        return value.quantize(Decimal('0.01'))
    return Decimal(str(value)).quantize(Decimal('0.01'))


def load_source_rows(source_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    engine = create_engine(source_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        clients = list(conn.execute(text(
            'SELECT id, user, pass, nome, nif, email, telefone, admin, activo, criado_em, ultimo_login, developer '
            'FROM clientes ORDER BY id'
        )).mappings())
        orders = list(conn.execute(text(
            'SELECT id, cliente_id, cliente_nome, cliente_nif, total, unidades, linhas, notas, criado_em, request_id, public_number, order_status, email_status, email_error, email_sent_at '
            'FROM encomendas ORDER BY id'
        )).mappings())
        lines = list(conn.execute(text(
            'SELECT id, encomenda_id, ref, nome, tipo, cor, tamanho, quantidade, preco_unit, total_linha '
            'FROM encomenda_linhas ORDER BY encomenda_id, id'
        )).mappings())
    return clients, orders, lines


def ensure_product_for_legacy_order(db: Session, line: dict[str, Any]) -> Product:
    ref = normalize_text(line['ref'])
    product = db.scalar(select(Product).where(Product.ref == ref))
    if product is not None:
        return product
    product = Product(
        ref=ref,
        name=normalize_text(line.get('nome')) or ref,
        product_type=normalize_text(line.get('tipo')) or 'Artigo legado',
        category_slug=None,
        price=to_decimal(line.get('preco_unit'), Decimal('0.00')),
        pvp=None,
        colors_json=[],
        sizes_json=[],
        image_path=None,
        image_checksum=None,
        image_mime_type=None,
        sort_order=0,
        active=False,
        manual_active=False,
        season='ambos',
        quantity_step=1,
        description='Produto legado importado para preservar uma encomenda V1.',
        metadata_json={'source': 'v1-orders-legacy', 'legacy_order_line_ref': ref},
    )
    db.add(product)
    return product


def sync_users(db: Session, clients: list[dict[str, Any]]) -> dict[str, int]:
    existing_users = {user.username: user for user in db.execute(select(User)).scalars().all()}
    used_emails = {
        normalize_text(user.email).casefold()
        for user in existing_users.values()
        if normalize_text(user.email)
    }
    created = 0
    updated = 0
    source_by_id = {int(row['id']): row for row in clients}

    def unique_email(raw_email: str | None, source_client_id: int) -> tuple[str | None, str | None]:
        email = normalize_text(raw_email)
        if not email:
            return None, None
        candidate = email
        candidate_key = candidate.casefold()
        if candidate_key in used_emails:
            if '@' in email:
                local, domain = email.split('@', 1)
                candidate = f'{local}+v1-{source_client_id}@{domain}'
            else:
                candidate = f'{email}+v1-{source_client_id}@example.test'
            suffix = 2
            while candidate.casefold() in used_emails:
                if '@' in candidate:
                    local, domain = candidate.split('@', 1)
                    candidate = f'{local}-{suffix}@{domain}'
                else:
                    candidate = f'{candidate}-{suffix}'
                suffix += 1
        used_emails.add(candidate.casefold())
        return candidate, email

    for row in clients:
        username = normalize_text(row.get('user'))
        if not username:
            continue
        user = existing_users.get(username)
        if user is None:
            user = User(username=username, password_hash=hash_password(str(row.get('pass') or username)), full_name=normalize_text(row.get('nome')) or username)
            db.add(user)
            existing_users[username] = user
            created += 1
        else:
            updated += 1
            if not user.password_hash or user.password_hash.startswith('argon2'):
                pass
        source_client_id = int(row.get('id') or 0)
        email_value, original_email = unique_email(row.get('email'), source_client_id)
        user.full_name = normalize_text(row.get('nome')) or username
        user.email = email_value
        user.nif = normalize_text(row.get('nif')) or None
        user.company_name = None
        user.password_hash = hash_password(str(row.get('pass') or username))
        user.role = 'admin' if row.get('admin') else 'developer' if row.get('developer') else 'client'
        user.active = bool(row.get('activo', 1))
        user.phone = normalize_text(row.get('telefone')) or None
        user.last_login_at = row.get('ultimo_login') if isinstance(row.get('ultimo_login'), datetime) else None
        user.metadata_json = {
            'source': 'v1',
            'source_client_id': source_client_id,
            'source_email': original_email,
            'imported_email': email_value,
            'source_created_at': row.get('criado_em').isoformat() if isinstance(row.get('criado_em'), datetime) else None,
        }
        if isinstance(row.get('criado_em'), datetime):
            user.created_at = row['criado_em']
        if isinstance(row.get('ultimo_login'), datetime):
            user.last_login_at = row['ultimo_login']

    db.flush()
    return {'created': created, 'updated': updated, 'source_by_id': source_by_id}


def sync_orders(db: Session, orders: list[dict[str, Any]], lines: list[dict[str, Any]], source_clients_by_id: dict[int, dict[str, Any]]) -> dict[str, int]:
    orders_by_id: dict[int, list[dict[str, Any]]] = {}
    for line in lines:
        orders_by_id.setdefault(int(line['encomenda_id']), []).append(line)

    users = {user.username: user for user in db.execute(select(User)).scalars().all()}
    products = {product.ref: product for product in db.execute(select(Product)).scalars().all()}
    created = 0
    updated = 0
    line_count = 0
    request_id_count = 0

    for order_row in orders:
        source_order_id = int(order_row['id'])
        source_client_id = int(order_row['cliente_id'] or 0)
        source_client = source_clients_by_id.get(source_client_id)
        if not source_client:
            continue
        username = normalize_text(source_client.get('user'))
        user = users.get(username)
        if user is None:
            continue

        request_id = normalize_text(order_row.get('request_id')) or f'legacy-v1-order-{source_order_id}'
        existing = db.scalar(select(Order).where(Order.request_id == request_id))
        if existing is None:
            public_number_source = normalize_text(order_row.get('public_number')) or public_order_number(
                (order_row.get('criado_em') or datetime.utcnow()).year,
                source_order_id,
            )
            public_number = public_number_source
            if db.scalar(select(Order.id).where(Order.public_number == public_number)) is not None:
                public_number = f'V1-{public_number_source}' if public_number_source else f'V1-{source_order_id:06d}'
            if db.scalar(select(Order.id).where(Order.public_number == public_number)) is not None:
                public_number = f'V1-{source_order_id:06d}'
            existing = db.scalar(select(Order).where(Order.public_number == public_number))
        else:
            public_number = existing.public_number
        if existing is None:
            order = Order(
                public_number=public_number,
                request_id=request_id,
                user_id=user.id,
                created_by_user_id=user.id,
                origin='legacy-v1',
                customer_name=normalize_text(order_row.get('cliente_nome')) or user.full_name,
                customer_nif=normalize_text(order_row.get('cliente_nif')) or None,
                customer_email=user.email,
                customer_phone=user.phone,
                customer_company=user.company_name,
                customer_address_line1=user.address_line1,
                customer_address_line2=user.address_line2,
                customer_postal_code=user.postal_code,
                customer_city=user.city,
                customer_country=user.country,
                subtotal=to_decimal(order_row.get('total'), Decimal('0.00')),
                total=to_decimal(order_row.get('total'), Decimal('0.00')),
                units=int(order_row.get('unidades') or 0),
                lines=int(order_row.get('linhas') or 0),
                notes=normalize_text(order_row.get('notas')) or None,
                order_status='shipped' if normalize_text(order_row.get('order_status')) == 'sent' else 'pending',
                confirmed_at=order_row.get('criado_em') if normalize_text(order_row.get('order_status')) in {'sent', 'pending'} else None,
                email_status=normalize_text(order_row.get('email_status')) or ('sent' if normalize_text(order_row.get('order_status')) == 'sent' else 'pending'),
                email_error=normalize_text(order_row.get('email_error')) or None,
                email_sent_at=order_row.get('email_sent_at') if isinstance(order_row.get('email_sent_at'), datetime) else None,
                customer_snapshot_json={
                    'source': 'v1',
                    'source_client_id': source_client_id,
                    'username': username,
                    'name': normalize_text(source_client.get('nome')) or username,
                    'nif': normalize_text(source_client.get('nif')) or None,
                    'email': normalize_text(source_client.get('email')) or None,
                    'phone': normalize_text(source_client.get('telefone')) or None,
                },
                snapshot_json={
                    'source': 'v1',
                    'legacy_order_id': source_order_id,
                    'legacy_client_id': source_client_id,
                    'legacy_request_id': normalize_text(order_row.get('request_id')) or None,
                    'legacy_public_number': normalize_text(order_row.get('public_number')) or None,
                    'legacy_status': normalize_text(order_row.get('order_status')) or None,
                },
            )
            if isinstance(order_row.get('criado_em'), datetime):
                order.created_at = order_row['criado_em']
            db.add(order)
            db.flush()
            created += 1
        else:
            order = existing
            order.user_id = user.id
            order.created_by_user_id = user.id
            order.origin = 'legacy-v1'
            order.customer_name = normalize_text(order_row.get('cliente_nome')) or user.full_name
            order.customer_nif = normalize_text(order_row.get('cliente_nif')) or None
            order.customer_email = user.email
            order.customer_phone = user.phone
            order.customer_company = user.company_name
            order.customer_address_line1 = user.address_line1
            order.customer_address_line2 = user.address_line2
            order.customer_postal_code = user.postal_code
            order.customer_city = user.city
            order.customer_country = user.country
            order.subtotal = to_decimal(order_row.get('total'), Decimal('0.00'))
            order.total = to_decimal(order_row.get('total'), Decimal('0.00'))
            order.units = int(order_row.get('unidades') or 0)
            order.lines = int(order_row.get('linhas') or 0)
            order.notes = normalize_text(order_row.get('notas')) or None
            order.order_status = 'shipped' if normalize_text(order_row.get('order_status')) == 'sent' else 'pending'
            order.confirmed_at = order_row.get('criado_em') if normalize_text(order_row.get('order_status')) in {'sent', 'pending'} else None
            order.email_status = normalize_text(order_row.get('email_status')) or ('sent' if normalize_text(order_row.get('order_status')) == 'sent' else 'pending')
            order.email_error = normalize_text(order_row.get('email_error')) or None
            order.email_sent_at = order_row.get('email_sent_at') if isinstance(order_row.get('email_sent_at'), datetime) else None
            order.customer_snapshot_json = {
                'source': 'v1',
                'source_client_id': source_client_id,
                'username': username,
                'name': normalize_text(source_client.get('nome')) or username,
                'nif': normalize_text(source_client.get('nif')) or None,
                'email': normalize_text(source_client.get('email')) or None,
                'phone': normalize_text(source_client.get('telefone')) or None,
            }
            order.snapshot_json = {
                'source': 'v1',
                'legacy_order_id': source_order_id,
                'legacy_client_id': source_client_id,
                'legacy_request_id': normalize_text(order_row.get('request_id')) or None,
                'legacy_public_number': normalize_text(order_row.get('public_number')) or None,
                'legacy_status': normalize_text(order_row.get('order_status')) or None,
            }
            updated += 1

        existing_request = db.get(OrderRequestId, request_id)
        if existing_request is None:
            db.add(OrderRequestId(request_id=request_id, order_id=order.id, request_hash=f'legacy-v1-{source_order_id:08d}'))
            request_id_count += 1
        else:
            existing_request.order_id = order.id
            existing_request.request_hash = f'legacy-v1-{source_order_id:08d}'

        db.execute(OrderLine.__table__.delete().where(OrderLine.order_id == order.id))
        for line in orders_by_id.get(source_order_id, []):
            ref = normalize_text(line.get('ref'))
            product = products.get(ref)
            if product is None:
                product = ensure_product_for_legacy_order(db, line)
                products[product.ref] = product
            db.add(
                OrderLine(
                    order_id=order.id,
                    product_ref=product.ref,
                    product_name=normalize_text(line.get('nome')) or product.name,
                    product_type=normalize_text(line.get('tipo')) or product.product_type,
                    color=normalize_text(line.get('cor')) or '',
                    size=normalize_text(line.get('tamanho')) or '',
                    quantity=int(line.get('quantidade') or 0),
                    unit_price=to_decimal(line.get('preco_unit'), product.price),
                    line_total=to_decimal(line.get('total_linha'), Decimal('0.00')),
                    snapshot_json={
                        'source': 'v1',
                        'legacy_line_id': int(line.get('id') or 0),
                        'legacy_order_id': source_order_id,
                        'legacy_ref': ref,
                    },
                )
            )
            line_count += 1

    db.commit()
    return {'created': created, 'updated': updated, 'request_ids': request_id_count, 'lines': line_count}


def main() -> int:
    load_env_file(ROOT / '.env')
    parser = argparse.ArgumentParser(description='Import Villas V1 customers and orders into Villas V2')
    parser.add_argument('--source', default=None, help='Source database URL for Villas V1')
    parser.add_argument('--target', choices=['test', 'production'], default='production', help='Destination database')
    parser.add_argument('--dry-run', action='store_true', help='Do not write changes')
    args = parser.parse_args()

    source_url = args.source or resolve_source_url()
    target_url = resolve_target_url(args.target)
    target_engine = create_engine(target_url, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(bind=target_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    clients, orders, lines = load_source_rows(source_url)
    with SessionLocal() as db:
        users_result = sync_users(db, clients)
        if args.dry_run:
            db.rollback()
            print(json.dumps({
                'mode': 'dry-run',
                'source_clients': len(clients),
                'source_orders': len(orders),
                'source_lines': len(lines),
                'users_created': users_result['created'],
                'users_updated': users_result['updated'],
                'orders_created': 0,
                'orders_updated': 0,
                'order_request_ids_created': 0,
                'order_lines_written': 0,
            }, ensure_ascii=False, indent=2))
            return 0
        orders_result = sync_orders(db, orders, lines, users_result['source_by_id'])
        print(json.dumps({
            'mode': 'apply',
            'source_clients': len(clients),
            'source_orders': len(orders),
            'source_lines': len(lines),
            'users_created': users_result['created'],
            'users_updated': users_result['updated'],
            'orders_created': orders_result['created'],
            'orders_updated': orders_result['updated'],
            'order_request_ids_created': orders_result['request_ids'],
            'order_lines_written': orders_result['lines'],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
