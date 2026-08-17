from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy import func, select

from app.db import SessionLocal
from app.email_service import EmailService
from app.models import Base, EmailDeliveryLog, Order, OrderRequestId, OrderStatusHistory, Product, User
from app.order_service import OrderService
from app.pdf_service import build_order_pdf
from app.services import UserAdminService


def _csrf_headers(client):
    token = client.cookies.get('villas_v2_csrf')
    return {'X-CSRF-Token': token} if token else {}


def _create_user(*, username: str, role: str, email: str | None = None) -> None:
    with SessionLocal() as db:
        UserAdminService().create_user(
            db,
            username=username,
            password='secret123',
            full_name=f'{username} name',
            role=role,
            email=email or f'{username}@example.test',
            active=True,
        )


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


def _add_item(client, ref: str, *, key: str, quantity: int = 12, revision: int = 0) -> None:
    response = client.post(
        '/me/cart/items',
        headers=_csrf_headers(client),
        json={
            'idempotency_key': key,
            'cart_revision': revision,
            'ref': ref,
            'color': 'PRETO',
            'size': 'M',
            'quantity': quantity,
        },
    )
    assert response.status_code == 200


def _user_id(username: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def test_order_submit_is_idempotent_and_clears_cart(client):
    client_name = f'client_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=client_name, role='client')
    _create_product(ref)
    _login(client, client_name)

    _add_item(client, ref, key='cart-add-1', quantity=324)

    response = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={'idempotency_key': 'order-submit-1', 'cart_revision': 1, 'notes': 'Entrega normal'},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload['ok'] is True
    assert payload['order']['publicNumber'].startswith('VLS-')
    assert payload['order']['units'] == 324
    assert payload['order']['lines'] == 1

    retry = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={'idempotency_key': 'order-submit-1', 'cart_revision': 1, 'notes': 'Entrega normal'},
    )
    assert retry.status_code == 201
    assert retry.json()['order']['id'] == payload['order']['id']
    assert retry.json()['order']['publicNumber'] == payload['order']['publicNumber']

    cart = client.get('/me/cart?output=json')
    assert cart.status_code == 200
    assert cart.json()['cart']['units'] == 0
    assert cart.json()['cart']['revision'] == 2

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.scalar(select(func.count()).select_from(OrderRequestId)) == 1
        assert db.scalar(select(func.count()).select_from(OrderStatusHistory)) == 1

    order_page = client.get(f"/me/encomendas/{payload['order']['publicNumber']}")
    assert order_page.status_code == 200
    assert payload['order']['publicNumber'] in order_page.text


def test_client_order_requires_minimum_total(client):
    client_name = f'client_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=client_name, role='client')
    _create_product(ref)
    _login(client, client_name)
    _add_item(client, ref, key='cart-minimum', quantity=12)

    response = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={'idempotency_key': 'order-below-minimum', 'cart_revision': 1},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'minimum_order_total'
    assert client.get('/me/cart?output=json').json()['cart']['units'] == 12


def test_admin_can_submit_own_cart_for_selected_client(client):
    admin_name = f'admin_{uuid4().hex}'
    client_name = f'client_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=admin_name, role='admin')
    _create_user(username=client_name, role='client')
    _create_product(ref)
    _login(client, admin_name)
    _add_item(client, ref, key='admin-cart-add', quantity=324)

    response = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={
            'idempotency_key': 'admin-cart-submit',
            'cart_revision': 1,
            'customer_user_id': _user_id(client_name),
        },
    )
    assert response.status_code == 201
    payload = response.json()['order']
    assert payload['userId'] == _user_id(client_name)
    assert payload['origin'] == 'admin_cart'
    assert client.get('/me/cart?output=json').json()['cart']['units'] == 0


def test_order_status_transition_is_audited_and_not_duplicated(client):
    client_name = f'client_{uuid4().hex}'
    admin_name = f'admin_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=client_name, role='client')
    _create_user(username=admin_name, role='admin')
    _create_product(ref)

    _login(client, client_name)
    _add_item(client, ref, key='cart-add-2', quantity=324)
    order = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={'idempotency_key': 'order-submit-2', 'cart_revision': 1},
    ).json()['order']

    _login(client, admin_name)
    first = client.post(
        f"/admin/encomendas/{order['publicNumber']}/status",
        data={'csrf_token': client.cookies.get('villas_v2_csrf', ''), 'new_status': 'confirmed', 'note': 'ok'},
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        f"/admin/encomendas/{order['publicNumber']}/status",
        data={'csrf_token': client.cookies.get('villas_v2_csrf', ''), 'new_status': 'confirmed', 'note': 'ok'},
        follow_redirects=False,
    )
    assert second.status_code == 303

    with SessionLocal() as db:
        stored = db.scalar(select(Order).where(Order.public_number == order['publicNumber']))
        assert stored is not None
        assert stored.order_status == 'confirmed'
        assert db.scalar(select(func.count()).select_from(OrderStatusHistory).where(OrderStatusHistory.order_id == stored.id)) == 2


def test_email_service_marks_order_and_logs_delivery():
    username = f'client_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=username, role='client', email=f'{username}@example.test')
    _create_product(ref)

    service = OrderService()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        cart = service._lock_cart(db, user.id)
        # Seed one cart item directly through the authoritative cart model.
        product = db.scalar(select(Product).where(Product.ref == ref))
        assert product is not None
        from app.models import CartItem
        cart.items.append(
            CartItem(
                product_ref=product.ref,
                color='PRETO',
                size='M',
                quantity=324,
                unit_price_snapshot=product.price,
                line_total_snapshot=Decimal('255.96'),
                product_name_snapshot=product.name,
                product_type_snapshot=product.product_type,
                product_image_snapshot=product.image_path,
                product_snapshot={'ref': product.ref},
            )
        )
        db.commit()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user_id = user.id

    with SessionLocal() as db:
        order = service.submit_order(
            db,
            user_id=user_id,
            idempotency_key='email-order-1',
            request_id='req-1',
            cart_revision=0,
            notes=None,
        )
        sent_messages = []
        fake_smtp = SimpleNamespace(send_message=lambda message: sent_messages.append(message) or {'accepted': 1}, quit=lambda: None)
        settings = SimpleNamespace(smtp_host='smtp.example.test', smtp_port=587, smtp_user='sender@example.test', smtp_password='secret', smtp_from='sender@example.test', public_url='https://example.test')
        result = EmailService(settings=settings, transport_factory=lambda _settings: fake_smtp).send_order_event(
            db,
            order=order,
            event='order_received',
            request_id='req-1',
            related_user_id=user.id,
        )
        assert result.status == 'sent'
        assert 'PORTAL COMERCIAL' in sent_messages[0].get_body(preferencelist=('html',)).get_content()
        assert 'Ver encomenda' in sent_messages[0].get_body(preferencelist=('html',)).get_content()
        stored = db.scalar(select(Order).where(Order.id == order['id']))
        assert stored is not None
        assert stored.email_status == 'sent'
        assert db.scalar(select(func.count()).select_from(EmailDeliveryLog).where(EmailDeliveryLog.related_order_id == order['id'])) == 1
        pdf_bytes = build_order_pdf(order)
        assert pdf_bytes.startswith(b'%PDF-')


def test_email_service_sends_new_user_credentials():
    username = f'client_{uuid4().hex}'
    _create_user(username=username, role='client', email=f'{username}@example.test')
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        sent_messages = []
        fake_smtp = SimpleNamespace(send_message=lambda message: sent_messages.append(message) or {}, quit=lambda: None)
        settings = SimpleNamespace(smtp_host='smtp.example.test', smtp_port=587, smtp_user='sender@example.test', smtp_password='secret', smtp_from='sender@example.test', public_url='https://example.test')
        result = EmailService(settings=settings, transport_factory=lambda _settings: fake_smtp).send_user_created(
            db, user=user, password='temporary-password', request_id='welcome-1'
        )
        assert result.status == 'sent'
        assert len(sent_messages) == 1
        assert 'temporary-password' in sent_messages[0].get_body(preferencelist=('plain',)).get_content()
        assert 'Entrar no portal' in sent_messages[0].get_body(preferencelist=('html',)).get_content()
        assert db.scalar(select(func.count()).select_from(EmailDeliveryLog).where(EmailDeliveryLog.related_user_id == user.id)) == 1


def test_order_pdf_has_distinct_priced_and_unpriced_documents():
    items = [{
        'ref': '2145', 'name': 'Lycra seda 15 DEN', 'color': '["PRETO"]', 'size': '["Único"]',
        'quantity': 12, 'unitPrice': '0.79', 'lineTotal': '9.48',
    }]
    order = {
        'id': 42, 'publicNumber': 'VLS-2026-000042', 'createdAt': '2026-08-16T15:30:00',
        'orderStatus': 'confirmed', 'customerName': 'Cliente PDF', 'customerNif': '500000000',
        'items': items, 'lines': 1, 'units': 12, 'subtotal': '9.48', 'total': '9.48',
    }
    priced = PdfReader(BytesIO(build_order_pdf(order)))
    unpriced = PdfReader(BytesIO(build_order_pdf(order, hide_prices=True)))
    priced_text = '\n'.join(page.extract_text() or '' for page in priced.pages)
    unpriced_text = '\n'.join(page.extract_text() or '' for page in unpriced.pages)
    assert 'NOTA DE ENCOMENDA' in priced_text
    assert 'PREÇO UNIT.' in priced_text
    assert '9,48' in priced_text
    assert 'GUIA DE PREPARAÇÃO' in unpriced_text
    assert 'DOCUMENTO SEM PREÇOS' in unpriced_text
    assert 'PREÇO UNIT.' not in unpriced_text
    assert '9,48' not in unpriced_text
    assert '["' not in priced_text


def test_order_pdf_paginates_large_orders_and_repeats_table_header():
    items = [
        {'ref': f'REF-{index:03d}', 'name': f'Produto longo para validar paginação número {index}', 'color': 'PRETO', 'size': 'M/L', 'quantity': 12, 'unitPrice': '1.00', 'lineTotal': '12.00'}
        for index in range(1, 75)
    ]
    order = {'id': 99, 'publicNumber': 'VLS-2026-000099', 'orderStatus': 'pending', 'customerName': 'Cliente Longo', 'items': items, 'lines': len(items), 'units': 888, 'subtotal': '888.00', 'total': '888.00'}
    reader = PdfReader(BytesIO(build_order_pdf(order)))
    assert len(reader.pages) >= 3
    for page in reader.pages:
        text = page.extract_text() or ''
        assert 'VILLAS' in text
        assert 'Página' in text
