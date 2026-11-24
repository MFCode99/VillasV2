from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy import func, select

from app.db import SessionLocal
from app.email_service import EmailService
from app.models import Base, Catalog, EmailDeliveryLog, Order, OrderRequestId, OrderStatusHistory, Product, User
from app.order_service import OrderService, _next_public_order_number
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


def test_utilities_unit_price_keeps_three_decimals_and_rounds_customer_totals():
    ref = f'INT{uuid4().hex[:6]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'interpilhas') is None:
            db.add(Catalog(slug='interpilhas', label='Interpilhas', sort_order=10, active=True))
        db.add(
            Product(
                ref=ref,
                catalog_slug='interpilhas',
                name='Produto Interpilhas',
                product_type='Pilhas',
                category_slug=None,
                brand='Maxell',
                price=Decimal('1.301'),
                price_base=Decimal('1.301'),
                eco_value=Decimal('0.000'),
                pvp=None,
                colors_json=[],
                sizes_json=[],
                sort_order=1,
                active=True,
                manual_active=True,
                season='ambos',
                quantity_step=1,
                metadata_json={},
            )
        )
        db.commit()
        lines = OrderService()._hydrate_lines(db, [{'ref': ref, 'quantity': 10, 'color': '', 'size': ''}])

    assert len(lines) == 1
    assert lines[0].unit_price == Decimal('1.301')
    assert lines[0].line_total == Decimal('13.01')
    assert lines[0].snapshot_json['unit_price'] == '1.301'
    assert lines[0].snapshot_json['catalog_slug'] == 'interpilhas'


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
    assert payload['order']['notes'] == ''
    assert payload['order']['internalNotes'] == ''

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
        json={'idempotency_key': 'order-below-minimum', 'cart_revision': 1, 'ignore_minimum_total': True},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'minimum_order_total'
    assert client.get('/me/cart?output=json').json()['cart']['units'] == 12


def test_admin_can_ignore_minimum_total_from_cart(client):
    admin_name = f'admin_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=admin_name, role='admin')
    _create_product(ref)
    _login(client, admin_name)
    _add_item(client, ref, key='admin-below-minimum-add', quantity=12)

    response = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={'idempotency_key': 'admin-below-minimum-submit', 'cart_revision': 1, 'ignore_minimum_total': True},
    )
    assert response.status_code == 201
    payload = response.json()['order']
    assert Decimal(payload['total']) < Decimal('250.00')
    assert payload['snapshot']['ignored_minimum_total'] is True


def test_interpilhas_order_requires_300_euros_and_only_clears_its_cart(client):
    client_name = f'client_{uuid4().hex}'
    ref = f'INT{uuid4().hex[:6]}'
    _create_user(username=client_name, role='client')
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == client_name))
        user.metadata_json = {**(user.metadata_json or {}), 'catalog_access': ['villas', 'interpilhas']}
        if db.get(Catalog, 'interpilhas') is None:
            db.add(Catalog(slug='interpilhas', label='Interpilhas', sort_order=10, active=True))
        db.add(Product(ref=ref, catalog_slug='interpilhas', name='Produto Interpilhas', product_type='Pilhas', price=Decimal('10.000'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}))
        db.commit()
    _login(client, client_name)
    add = client.post('/me/cart/items', headers=_csrf_headers(client), json={'catalog_slug': 'interpilhas', 'idempotency_key': 'inter-min-add', 'cart_revision': 0, 'ref': ref, 'color': '', 'size': '', 'quantity': 29})
    assert add.status_code == 200
    item_id = add.json()['cart']['items'][0]['id']

    below = client.post('/me/orders', headers={**_csrf_headers(client), 'Accept': 'application/json'}, json={'catalog_slug': 'interpilhas', 'idempotency_key': 'inter-min-below', 'cart_revision': 1})
    assert below.status_code == 400
    assert below.json()['detail'] == 'minimum_order_total_interpilhas'

    updated = client.patch(f'/me/cart/items/{item_id}', headers=_csrf_headers(client), json={'catalog_slug': 'interpilhas', 'idempotency_key': 'inter-min-update', 'cart_revision': 1, 'quantity': 30})
    assert updated.status_code == 200
    created = client.post('/me/orders', headers={**_csrf_headers(client), 'Accept': 'application/json'}, json={'catalog_slug': 'interpilhas', 'idempotency_key': 'inter-min-ok', 'cart_revision': 2})
    assert created.status_code == 201
    assert created.json()['order']['catalogSlug'] == 'interpilhas'
    assert client.get('/me/cart?output=json&catalog=interpilhas').json()['cart']['units'] == 0


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
    assert payload['orderStatus'] == 'confirmed'
    assert payload['confirmedAt']
    assert client.get('/me/cart?output=json').json()['cart']['units'] == 0


def test_admin_can_submit_own_cart_for_self_without_selecting_client(client):
    admin_name = f'admin_{uuid4().hex}'
    ref = f'ORD{uuid4().hex[:6]}'
    _create_user(username=admin_name, role='admin')
    _create_product(ref)
    _login(client, admin_name)
    _add_item(client, ref, key='admin-self-cart-add', quantity=324)
    cart = client.get('/me/cart?output=json').json()['cart']
    item_id = cart['items'][0]['id']
    adjusted = client.patch(
        f'/me/cart/items/{item_id}',
        headers=_csrf_headers(client),
        json={
            'idempotency_key': 'admin-self-ignore-step',
            'cart_revision': 1,
            'quantity': 325,
            'ignore_quantity_step': True,
        },
    )
    assert adjusted.status_code == 200
    assert adjusted.json()['cart']['units'] == 325

    response = client.post(
        '/me/orders',
        headers={**_csrf_headers(client), 'Accept': 'application/json'},
        json={
            'idempotency_key': 'admin-self-cart-submit',
            'cart_revision': 2,
            'customer_user_id': None,
            'ignore_quantity_step': True,
        },
    )
    assert response.status_code == 201
    payload = response.json()['order']
    assert payload['userId'] == _user_id(admin_name)
    assert payload['createdByUserId'] == _user_id(admin_name)
    assert payload['orderStatus'] == 'confirmed'
    assert payload['confirmedAt']
    assert payload['units'] == 325
    assert payload['snapshot']['ignored_quantity_step'] is True
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
        assert 'VITOR GOUVEIA' in sent_messages[0].get_body(preferencelist=('html',)).get_content()
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
    assert 'COR' in priced_text and 'TAM.' in priced_text
    assert '9,48' in priced_text
    assert 'GUIA DE PREPARAÇÃO' in unpriced_text
    assert 'DOCUMENTO SEM PREÇOS' in unpriced_text
    assert 'VARIANTES' in unpriced_text
    assert 'PREÇO UNIT.' not in unpriced_text
    assert '9,48' not in unpriced_text
    assert '["' not in priced_text


def test_order_pdf_groups_categories_references_and_variants():
    items = [
        {'ref': '2145', 'name': 'Mini meia', 'color': 'PRETO', 'size': 'Único', 'quantity': 12, 'unitPrice': '0.79', 'lineTotal': '9.48', 'categoryLabel': 'Mini meia', 'categorySortOrder': 20},
        {'ref': '099', 'name': 'Soquete', 'color': 'BRANCO', 'size': '35-38', 'quantity': 12, 'unitPrice': '1.25', 'lineTotal': '15.00', 'categoryLabel': 'Soquetes', 'categorySortOrder': 10},
        {'ref': '2145', 'name': 'Mini meia', 'color': 'MUSKADE', 'size': 'Único', 'quantity': 24, 'unitPrice': '0.79', 'lineTotal': '18.96', 'categoryLabel': 'Mini meia', 'categorySortOrder': 20},
        {'ref': '4424a', 'name': 'Collant criança', 'color': 'MARINHO', 'size': '8', 'quantity': 12, 'unitPrice': '2.00', 'lineTotal': '24.00', 'categoryLabel': 'Collants', 'categorySortOrder': 30},
        {'ref': '4424b', 'name': 'Collant criança', 'color': 'PRETO', 'size': '12', 'quantity': 12, 'unitPrice': '2.00', 'lineTotal': '24.00', 'categoryLabel': 'Collants', 'categorySortOrder': 30},
    ]
    order = {
        'publicNumber': 'VLS-2026-000044', 'orderStatus': 'confirmed', 'customerName': 'Cliente PDF',
        'customerCarrier': 'Transportadora Teste', 'items': items, 'lines': 5, 'units': 72,
        'subtotal': '91.44', 'total': '91.44',
    }
    reader = PdfReader(BytesIO(build_order_pdf(order, hide_prices=True)))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert text.index('SOQUETES') < text.index('MINI MEIA') < text.index('COLLANTS')
    assert text.count('2145') == 1
    assert 'PRETO' in text and 'MUSKADE' in text
    assert '4424-8' in text and '4424-12' in text
    assert '4424a' not in text and '4424b' not in text
    assert 'Transportadora Teste' in text


def test_priced_order_pdf_keeps_original_flat_table():
    order = {
        'publicNumber': 'VLS-2026-000045', 'orderStatus': 'confirmed', 'customerName': 'Cliente PDF',
        'customerCarrier': 'Transportadora que não pertence ao modelo antigo',
        'items': [
            {'ref': '2145', 'name': 'Mini meia', 'color': 'PRETO', 'size': 'Único', 'quantity': 12, 'unitPrice': '0.79', 'lineTotal': '9.48', 'categoryLabel': 'Mini meia'},
            {'ref': '2145', 'name': 'Mini meia', 'color': 'MUSKADE', 'size': 'Único', 'quantity': 24, 'unitPrice': '0.79', 'lineTotal': '18.96', 'categoryLabel': 'Mini meia'},
        ],
        'lines': 2, 'units': 36, 'subtotal': '28.44', 'total': '28.44',
    }
    reader = PdfReader(BytesIO(build_order_pdf(order)))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'ARTIGOS POR CATEGORIA' not in text
    assert text.count('2145') == 2
    assert 'PREÇO UNIT.' in text
    assert 'Transportadora que não pertence ao modelo antigo' not in text


def test_no_price_pdf_layout_can_hide_blocks_and_product_name():
    order = {
        'publicNumber': 'VLS-2026-000046', 'orderStatus': 'confirmed', 'customerName': 'Cliente escondido',
        'customerEmail': 'cliente@example.test', 'customerCarrier': 'Transportadora escondida',
        'items': [{'ref': '099', 'name': 'Nome escondido', 'color': 'PRETO', 'size': 'M', 'quantity': 12, 'categoryLabel': 'Soquetes'}],
        'lines': 1, 'units': 12, 'subtotal': '0', 'total': '0',
    }
    layout = {
        'showCustomer': False, 'showContact': False, 'showCarrier': False,
        'showProductName': False, 'showSummary': False, 'showCategories': False,
        'blankColumn': True, 'fontSize': 'large',
    }
    reader = PdfReader(BytesIO(build_order_pdf(order, hide_prices=True, layout=layout)))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'Cliente escondido' not in text
    assert 'cliente@example.test' not in text
    assert 'Transportadora escondida' not in text
    assert 'Nome escondido' not in text
    assert 'SOQUETES' not in text


def test_order_pdf_does_not_render_internal_notes():
    order = {
        'id': 43, 'publicNumber': 'VLS-2026-000043', 'createdAt': '2026-08-16T15:30:00',
        'orderStatus': 'confirmed', 'customerName': 'Cliente PDF', 'items': [],
        'lines': 0, 'units': 0, 'subtotal': '0.00', 'total': '0.00',
        'notes': 'Nota interna que nunca deve sair',
        'internalNotes': 'Nota interna que nunca deve sair',
    }
    reader = PdfReader(BytesIO(build_order_pdf(order)))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'Nota interna que nunca deve sair' not in text
    assert 'NOTAS' not in text


def test_public_order_number_skips_existing_sequence():
    username = f'client_{uuid4().hex}'
    _create_user(username=username, role='client')
    with SessionLocal() as db:
        existing = Order(
            public_number='VLS-2026-000033',
            request_id=f'existing-{uuid4().hex}',
            user_id=_user_id(username),
            customer_name='Cliente existente',
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            units=0,
            lines=0,
        )
        db.add(existing)
        db.commit()
        assert _next_public_order_number(db, 2026, 33) == 'VLS-2026-000034'


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
        assert 'VITOR GOUVEIA' in text
        assert 'Página' in text


def test_utilities_order_pdf_uses_public_catalog_name_without_supplier():
    order = {
        'id': 100,
        'publicNumber': 'VLS-2026-000100',
        'catalogSlug': 'interpilhas',
        'orderStatus': 'confirmed',
        'customerName': 'Cliente Utilidades',
        'items': [{'ref': 'BAT-1', 'name': 'Pilha', 'quantity': 30, 'unitPrice': '10.000', 'lineTotal': '300.00', 'catalogSlug': 'interpilhas'}],
        'lines': 1,
        'units': 30,
        'subtotal': '300.00',
        'total': '300.00',
    }
    text = '\n'.join((page.extract_text() or '') for page in PdfReader(BytesIO(build_order_pdf(order))).pages)
    no_price_text = '\n'.join((page.extract_text() or '') for page in PdfReader(BytesIO(build_order_pdf(order, hide_prices=True))).pages)
    normalized_text = text.upper()
    assert 'NOTA DE ENCOMENDA - UTILIDADES' in normalized_text
    assert 'VITOR GOUVEIA' in normalized_text
    assert 'INTERPILHAS' not in normalized_text
    assert 'COR' not in normalized_text and 'TAM.' not in normalized_text
    assert 'VARIANTES' not in no_price_text.upper()
    assert '- · -' not in no_price_text
