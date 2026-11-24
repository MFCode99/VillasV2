from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.cart_service import CartService
from app.db import SessionLocal, TestEngine
from app.models import Base, Cart, CartItem, CartOperation, Catalog, Product, User
from app.services import UserAdminService


def _mysql_only():
    return pytest.mark.skipif(TestEngine.url.get_backend_name() != 'mysql', reason='MySQL-only concurrency test')


def _create_user(*, username: str, role: str) -> None:
    with SessionLocal() as db:
        UserAdminService().create_user(
            db,
            username=username,
            password='secret123',
            full_name=f'{username} name',
            role=role,
            email=f'{username}@example.test',
            active=True,
        )


def _create_client(username: str) -> None:
    _create_user(username=username, role='client')


def _create_admin(username: str) -> None:
    _create_user(username=username, role='admin')


def _create_product(ref: str, *, step: int = 12) -> None:
    with SessionLocal() as db:
        Base.metadata.create_all(bind=db.get_bind(), checkfirst=True)
        db.add(
            Product(
                ref=ref,
                name='Lycra Seda 15 DEN',
                product_type='Mini Meia 2 Pares',
                category_slug=None,
                price=Decimal('0.79'),
                pvp=Decimal('1.95'),
                colors_json=['PRETO', 'AZUL'],
                sizes_json=['M', 'L'],
                image_path=None,
                image_checksum=None,
                image_mime_type=None,
                sort_order=1,
                active=True,
                manual_active=True,
                season='ambos',
                quantity_step=step,
                description=None,
                metadata_json={},
            )
        )
        db.commit()


def _login(client, username: str) -> None:
    response = client.post('/entrar', data={'username': username, 'password': 'secret123'}, follow_redirects=False)
    assert response.status_code == 303


def _csrf_headers(client):
    token = client.cookies.get('villas_v2_csrf')
    return {'X-CSRF-Token': token} if token else {}


def _add_item(client, ref: str, *, key: str, color: str = 'PRETO', size: str = 'M', quantity: int = 12, revision: int = 0, extra: dict | None = None):
    payload = {
        'idempotency_key': key,
        'cart_revision': revision,
        'ref': ref,
        'color': color,
        'size': size,
        'quantity': quantity,
    }
    if extra:
        payload.update(extra)
    return client.post('/me/cart/items', headers=_csrf_headers(client), json=payload)


def _user_id(username: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def _cart_state(user_id: int) -> dict[str, object]:
    service = CartService()
    with SessionLocal() as db:
        return service.get_cart(db, user_id)


def test_catalog_carts_are_isolated_with_independent_revisions(client):
    username = f'client_{uuid4().hex}'
    villas_ref = f'VIL{uuid4().hex[:6]}'
    interpilhas_ref = f'INT{uuid4().hex[:6]}'
    _create_client(username)
    _create_product(villas_ref, step=1)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        user.metadata_json = {**(user.metadata_json or {}), 'catalog_access': ['villas', 'interpilhas']}
        if db.get(Catalog, 'interpilhas') is None:
            db.add(Catalog(slug='interpilhas', label='Interpilhas', sort_order=10, active=True))
        db.add(Product(ref=interpilhas_ref, catalog_slug='interpilhas', name='Pilha teste', product_type='Pilha', price=Decimal('10.000'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}))
        db.commit()
    _login(client, username)

    villas_add = _add_item(client, villas_ref, key='split-villas-1', color='PRETO', size='M', quantity=1, extra={'catalog_slug': 'villas'})
    interpilhas_add = _add_item(client, interpilhas_ref, key='split-inter-1', color='', size='', quantity=30, revision=0, extra={'catalog_slug': 'interpilhas'})
    assert villas_add.status_code == 200
    assert interpilhas_add.status_code == 200
    assert villas_add.json()['cart']['revision'] == 1
    assert interpilhas_add.json()['cart']['revision'] == 1

    villas_cart = client.get('/me/cart?output=json&catalog=villas').json()['cart']
    interpilhas_cart = client.get('/me/cart?output=json&catalog=interpilhas').json()['cart']
    assert [item['ref'] for item in villas_cart['items']] == [villas_ref]
    assert [item['ref'] for item in interpilhas_cart['items']] == [interpilhas_ref]
    assert villas_cart['minimum_total'] == '250.00'
    assert interpilhas_cart['minimum_total'] == '300.00'

    second_villas = _add_item(client, villas_ref, key='split-villas-2', color='PRETO', size='M', quantity=1, revision=1, extra={'catalog_slug': 'villas'})
    assert second_villas.status_code == 200
    assert second_villas.json()['cart']['revision'] == 2
    assert client.get('/me/cart?output=json&catalog=interpilhas').json()['cart']['revision'] == 1


def test_cart_add_is_idempotent_and_quantity_step(client):
    username = f'client_{uuid4().hex}'
    ref = f'2145{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    _login(client, username)
    user_id = _user_id(username)

    first = _add_item(client, ref, key='add-1-aaaa', quantity=12, revision=0)
    assert first.status_code == 200
    first_cart = first.json()['cart']
    assert first_cart['units'] == 12
    assert first_cart['lines'] == 1
    assert first_cart['revision'] == 1

    retry = _add_item(client, ref, key='add-1-aaaa', quantity=12, revision=0)
    assert retry.status_code == 200
    assert retry.json()['cart']['units'] == 12
    assert retry.json()['cart']['revision'] == 1

    second = _add_item(client, ref, key='add-2-bbbb', quantity=12, revision=1)
    assert second.status_code == 200
    second_cart = second.json()['cart']
    assert second_cart['units'] == 24
    assert second_cart['lines'] == 1
    assert second_cart['revision'] == 2

    summary = client.get('/me/cart?output=json')
    assert summary.status_code == 200
    assert summary.json()['cart']['units'] == 24
    assert summary.json()['cart']['revision'] == 2

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CartOperation).where(CartOperation.user_id == user_id)) == 2
        assert db.scalar(select(func.count()).select_from(CartItem).where(CartItem.cart_user_id == user_id)) == 1


def test_cart_update_remove_and_revision_conflict(client):
    username = f'client_{uuid4().hex}'
    ref = f'2146{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    _login(client, username)

    add_response = _add_item(client, ref, key='add-3-cccc', quantity=12, revision=0)
    item_id = add_response.json()['cart']['items'][0]['id']

    update = client.patch(
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'update-1', 'cart_revision': 1, 'quantity': 24},
    )
    assert update.status_code == 200
    assert update.json()['cart']['units'] == 24
    assert update.json()['cart']['revision'] == 2

    stale = client.patch(
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'update-2', 'cart_revision': 1, 'quantity': 36},
    )
    assert stale.status_code == 409
    assert stale.json()['detail'] == 'cart_revision_mismatch'

    removed = client.request(
        'DELETE',
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'remove-1', 'cart_revision': 2},
    )
    assert removed.status_code == 200
    assert removed.json()['cart']['units'] == 0
    assert removed.json()['cart']['lines'] == 0
    assert removed.json()['cart']['revision'] == 3

    repeat_remove = client.request(
        'DELETE',
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'remove-1', 'cart_revision': 2},
    )
    assert repeat_remove.status_code == 200
    assert repeat_remove.json()['cart']['units'] == 0


def test_cart_rejects_invalid_variant_and_step(client):
    username = f'client_{uuid4().hex}'
    ref = f'2147{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref, step=12)
    _login(client, username)

    bad_color = _add_item(client, ref, key='bad-color', color='VERDE', quantity=12)
    assert bad_color.status_code == 400
    assert bad_color.json()['detail'] == 'invalid_color'

    bad_step = _add_item(client, ref, key='bad-step', quantity=13)
    assert bad_step.status_code == 400
    assert bad_step.json()['detail'] == 'invalid_quantity_step'

    valid = _add_item(client, ref, key='valid-step', quantity=12)
    item_id = valid.json()['cart']['items'][0]['id']
    client_override = client.patch(
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'client-ignore-step', 'cart_revision': 1, 'quantity': 13, 'ignore_quantity_step': True},
    )
    assert client_override.status_code == 400
    assert client_override.json()['detail'] == 'invalid_quantity_step'


def test_cart_mutations_require_csrf(client):
    username = f'client_{uuid4().hex}'
    ref = f'2148{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    _login(client, username)
    response = client.post(
        '/me/cart/items',
        json={'idempotency_key': 'csrf-test-1', 'cart_revision': 0, 'ref': ref, 'color': 'PRETO', 'size': 'M', 'quantity': 12},
    )
    assert response.status_code == 403


def test_admin_can_add_to_cart(client):
    username = f'admin_{uuid4().hex}'
    ref = f'2152{uuid4().hex[:4]}'
    _create_admin(username)
    _create_product(ref)
    _login(client, username)

    response = _add_item(client, ref, key='admin-add-1', quantity=12)
    assert response.status_code == 200
    payload = response.json()['cart']
    assert payload['units'] == 12
    assert payload['lines'] == 1
    assert client.get('/me/cart?output=json').status_code == 200


def test_price_and_mass_assignment_tampering_ignored(client):
    username = f'client_{uuid4().hex}'
    ref = f'2149{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    _login(client, username)

    response = _add_item(
        client,
        ref,
        key='tamper-1',
        quantity=12,
        extra={'price': '0.01', 'user_id': 999, 'cart_id': 999, 'role': 'admin'},
    )
    assert response.status_code == 200
    cart = response.json()['cart']
    assert cart['units'] == 12
    assert cart['items'][0]['unit_price'] == '0.79'


def test_idor_blocked_between_clients(client):
    username_a = f'client_{uuid4().hex}'
    username_b = f'client_{uuid4().hex}'
    ref = f'2150{uuid4().hex[:4]}'
    _create_client(username_a)
    _create_client(username_b)
    _create_product(ref)

    _login(client, username_a)
    add_response = _add_item(client, ref, key='idor-add', quantity=12)
    item_id = add_response.json()['cart']['items'][0]['id']

    _login(client, username_b)
    response = client.request(
        'DELETE',
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={'idempotency_key': 'idor-remove', 'cart_revision': 1},
    )
    assert response.status_code == 404
    assert response.json()['detail'] == 'cart_item_not_found'


def test_reference_search_add_cart_consistency(client):
    username = f'client_{uuid4().hex}'
    ref = f'2151{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    _login(client, username)

    assert client.get(f'/catalogo?ref={ref}').status_code == 200
    assert client.get(f'/catalogo/produto/{ref}').status_code == 200

    first = _add_item(client, ref, key='reg-0001', quantity=12)
    assert first.status_code == 200
    assert client.get('/me/cart?output=json').json()['cart']['units'] == 12

    second = _add_item(client, ref, key='reg-0002', quantity=12, revision=1)
    assert second.status_code == 200
    cart = client.get('/me/cart?output=json').json()['cart']
    assert cart['units'] == 24
    assert cart['lines'] == 1
    assert cart['revision'] == 2


@_mysql_only()
def test_concurrent_first_cart_creates_single_cart_and_canonical_state():
    username = f'client_{uuid4().hex}'
    ref_a = f'3001{uuid4().hex[:4]}'
    ref_b = f'3002{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref_a)
    _create_product(ref_b)
    user_id = _user_id(username)

    barrier = threading.Barrier(2)

    def worker(ref: str, key: str, color: str, size: str):
        with SessionLocal() as db:
            barrier.wait()
            return CartService().add_item(
                db,
                user_id=user_id,
                idempotency_key=key,
                ref=ref,
                color=color,
                size=size,
                quantity=12,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker, ref_a, 'first-a-aaaa', 'PRETO', 'M'),
            executor.submit(worker, ref_b, 'first-b-bbbb', 'AZUL', 'L'),
        ]
        results = [future.result() for future in futures]

    assert all(result['revision'] >= 1 for result in results)
    cart = _cart_state(user_id)
    assert cart['lines'] == 2
    assert cart['units'] == 24
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Cart).where(Cart.user_id == user_id)) == 1


@_mysql_only()
def test_concurrent_same_variant_increments_without_lost_update():
    username = f'client_{uuid4().hex}'
    ref = f'3003{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    user_id = _user_id(username)
    service = CartService()

    with SessionLocal() as db:
        service.add_item(
            db,
            user_id=user_id,
            idempotency_key='seed-aaaa',
            ref=ref,
            color='PRETO',
            size='M',
            quantity=12,
        )

    barrier = threading.Barrier(2)

    def worker(key: str):
        with SessionLocal() as db:
            barrier.wait()
            return service.add_item(
                db,
                user_id=user_id,
                idempotency_key=key,
                ref=ref,
                color='PRETO',
                size='M',
                quantity=12,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker, 'inc-a-bbbb'), executor.submit(worker, 'inc-b-cccc')]
        [future.result() for future in futures]

    cart = _cart_state(user_id)
    assert cart['lines'] == 1
    assert cart['units'] == 36


@_mysql_only()
def test_concurrent_duplicate_line_protection():
    username = f'client_{uuid4().hex}'
    ref = f'3004{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    user_id = _user_id(username)
    service = CartService()

    barrier = threading.Barrier(2)

    def worker(key: str):
        with SessionLocal() as db:
            barrier.wait()
            return service.add_item(
                db,
                user_id=user_id,
                idempotency_key=key,
                ref=ref,
                color='PRETO',
                size='M',
                quantity=12,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker, 'dup-a-aaaa'), executor.submit(worker, 'dup-b-bbbb')]
        [future.result() for future in futures]

    with SessionLocal() as db:
        assert db.scalar(select(func.count(CartItem.id)).where(CartItem.cart_user_id == user_id)) == 1
    cart = _cart_state(user_id)
    assert cart['lines'] == 1
    assert cart['units'] == 24


@_mysql_only()
def test_stale_revision_is_rejected():
    username = f'client_{uuid4().hex}'
    ref = f'3005{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    user_id = _user_id(username)
    service = CartService()

    with SessionLocal() as db:
        service.add_item(
            db,
            user_id=user_id,
            idempotency_key='stale-seed',
            ref=ref,
            color='PRETO',
            size='M',
            quantity=12,
        )

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            service.add_item(
                db,
                user_id=user_id,
                idempotency_key='stale-next',
                ref=ref,
                color='PRETO',
                size='M',
                quantity=12,
                expected_revision=0,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == 'cart_revision_mismatch'


@_mysql_only()
def test_idempotency_key_same_payload_same_result_and_different_payload_rejected():
    username = f'client_{uuid4().hex}'
    ref = f'3006{uuid4().hex[:4]}'
    _create_client(username)
    _create_product(ref)
    user_id = _user_id(username)
    service = CartService()

    with SessionLocal() as db:
        first = service.add_item(
            db,
            user_id=user_id,
            idempotency_key='idem-aaaa',
            ref=ref,
            color='PRETO',
            size='M',
            quantity=12,
        )
        second = service.add_item(
            db,
            user_id=user_id,
            idempotency_key='idem-aaaa',
            ref=ref,
            color='PRETO',
            size='M',
            quantity=12,
        )
        assert first == second

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            service.add_item(
                db,
                user_id=user_id,
                idempotency_key='idem-aaaa',
                ref=ref,
                color='AZUL',
                size='L',
                quantity=12,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == 'idempotency_key_conflict'

    cart = _cart_state(user_id)
    assert cart['lines'] == 1
    assert cart['units'] == 12
    with SessionLocal() as db:
        assert db.scalar(select(func.count(CartOperation.id)).where(CartOperation.user_id == user_id)) == 1
