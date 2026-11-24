from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.db import SessionLocal
from app.email_service import EmailSendResult
from app.models import Catalog, Order, OrderLine, Product, ProductImportBatch, SiteSetting
from app.services import UserAdminService
from app.system_monitor import MONITOR_RUN_KEY, run_monitor


def login_user(client, role='client'):
    username = f'{role}_{uuid4().hex}'
    with SessionLocal() as db:
        user = UserAdminService().create_user(db, username=username, password='secret123', full_name='Teste', role=role, active=True, email=f'{username}@example.test')
        user_id = user.id
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': 'secret123'})
    assert response.status_code == 200
    return response.json(), user_id


def test_customer_can_update_account_and_password(client):
    login, _ = login_user(client)
    headers = {'X-CSRF-Token': login['csrfToken']}
    payload = {
        'full_name': 'Cliente Atualizado', 'company_name': 'Empresa', 'email': 'novo@example.com',
        'additional_emails': ['compras@example.com'], 'phone': '910000000', 'nif': '', 'carrier': 'Transportadora',
        'address_line1': 'Rua Principal', 'address_line2': '', 'postal_code': '1000-100', 'city': 'Lisboa', 'country': 'Portugal',
        'delivery_same_as_billing': True, 'delivery_address_line1': '', 'delivery_address_line2': '',
        'delivery_postal_code': '', 'delivery_city': '', 'delivery_country': '',
    }
    updated = client.put('/api/v1/account', headers=headers, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()['user']['fullName'] == 'Cliente Atualizado'
    assert updated.json()['user']['additionalEmails'] == ['compras@example.com']
    password = client.put('/api/v1/account/password', headers=headers, json={'current_password': 'secret123', 'new_password': 'nova-password-123', 'confirmation': 'nova-password-123'})
    assert password.status_code == 200
    client.post('/api/v1/auth/logout', headers=headers)
    assert client.post('/api/v1/auth/login', json={'username': login['user']['username'], 'password': 'nova-password-123'}).status_code == 200


def test_customer_can_repeat_order_with_current_pack_step(client):
    login, user_id = login_user(client)
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'REP-{uuid4().hex[:8]}'
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
        product = Product(ref=ref, catalog_slug='villas', name='Produto repetível', product_type='Teste', price=Decimal('10.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=12, metadata_json={})
        order = Order(public_number=identifier, request_id=uuid4().hex, user_id=user_id, created_by_user_id=user_id, customer_name='Teste', subtotal=Decimal('10.00'), total=Decimal('10.00'), units=5, lines=1, snapshot_json={'catalog_slug': 'villas'})
        order.items.append(OrderLine(product_ref=ref, product_name=product.name, product_type=product.product_type, color='', size='', quantity=5, unit_price=Decimal('10.00'), line_total=Decimal('50.00'), snapshot_json={'catalog_slug': 'villas'}))
        db.add_all([product, order]); db.commit()
    response = client.post(f'/api/v1/orders/{identifier}/repeat', headers=headers, json={'idempotency_key': uuid4().hex})
    assert response.status_code == 200
    assert response.json()['cart']['items'][0]['quantity'] == 12


def test_product_import_history_can_rollback(client):
    login, _ = login_user(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'IMP-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True)); db.commit()
    committed = client.post('/api/v1/admin/import/products/commit', headers=headers, json={
        'filename': 'teste.xlsx', 'source_type': 'spreadsheet', 'catalog': 'villas', 'update_existing': True, 'categories': [],
        'rows': [{'ref': ref, 'catalog_slug': 'villas', 'name': 'Importado', 'product_type': 'Teste', 'price': '3.50', 'quantity_step': 1}],
    })
    assert committed.status_code == 200
    batch_id = committed.json()['batch']['id']
    assert client.get('/api/v1/admin/import/products/history').json()['batches'][0]['filename'] == 'teste.xlsx'
    rolled_back = client.post(f'/api/v1/admin/import/products/history/{batch_id}/rollback', headers=headers)
    assert rolled_back.status_code == 200
    assert rolled_back.json()['removed'] == 1
    with SessionLocal() as db:
        assert db.get(Product, ref) is None
        assert db.get(ProductImportBatch, batch_id).status == 'rolled_back'


def test_monitor_persists_health_snapshot(monkeypatch, tmp_path):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class Email:
        def health_check(self): return True
        def send_system_alert(self, *_args, **_kwargs): return EmailSendResult(status='sent')
    monkeypatch.setattr('app.system_monitor.urlopen', lambda *_args, **_kwargs: Response())
    settings = SimpleNamespace(media_root=Path(tmp_path), public_url='https://example.test')
    with SessionLocal() as db:
        result = run_monitor(db, settings, Email())
        assert result['ok'] is True
        assert db.get(SiteSetting, MONITOR_RUN_KEY) is not None
