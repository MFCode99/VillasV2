import io
import json
from decimal import Decimal
from uuid import uuid4

from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Order, Product
from app.services import UserAdminService


def _user(role='client'):
    username = f'{role}_{uuid4().hex}'
    with SessionLocal() as db:
        user = UserAdminService().create_user(
            db,
            username=username,
            password='secret123',
            full_name='API Test',
            role=role,
            active=True,
        )
        return username, user.id


def _api_login(client, role='client'):
    username, user_id = _user(role)
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': 'secret123'})
    assert response.status_code == 200
    return response.json(), user_id


def test_api_session_and_login(client):
    assert client.get('/api/v1/session').json()['authenticated'] is False
    payload, _ = _api_login(client)
    assert payload['user']['role'] == 'client'
    assert client.get('/api/v1/session').json()['authenticated'] is True


def test_api_rejects_private_data_without_session(client):
    assert client.get('/api/v1/catalog').status_code == 401
    assert client.get('/api/v1/admin/users').status_code == 401


def test_api_admin_can_create_and_toggle_user(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    username = f'new_{uuid4().hex}'
    response = client.post('/api/v1/admin/users', headers=headers, json={
        'username': username,
        'password': 'secret123',
        'full_name': 'Novo Cliente',
        'role': 'client',
        'active': True,
    })
    assert response.status_code == 201
    user = response.json()['user']
    toggle = client.patch(f"/api/v1/admin/users/{user['id']}/active", headers=headers, json={'active': False})
    assert toggle.status_code == 200
    assert toggle.json()['user']['active'] is False


def test_vue_history_routes_serve_built_app(client):
    response = client.get('/nova/admin/utilizadores')
    assert response.status_code == 200
    assert '<div id="app"></div>' in response.text


def _product_payload(ref):
    return {
        'ref': ref,
        'name': 'Produto transacional',
        'product_type': 'Teste',
        'category_slug': None,
        'price': '12.50',
        'pvp': None,
        'colors': [],
        'sizes': [],
        'season': 'ambos',
        'quantity_step': 1,
        'sort_order': 0,
        'active': True,
        'manual_active': True,
        'description': '',
    }


def test_product_transaction_rejects_fake_image_without_creating_product(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'fake-{uuid4().hex}'
    response = client.post(
        '/api/v1/admin/products/save',
        headers=headers,
        data={'payload': json.dumps(_product_payload(ref))},
        files={'image': ('not-an-image.jpg', b'this is not an image', 'image/jpeg')},
    )
    assert response.status_code == 400
    assert response.json()['detail'] == 'invalid_image_format'
    with SessionLocal() as db:
        assert db.get(Product, ref) is None


def test_product_transaction_converts_bmp_and_saves_everything(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'bmp-{uuid4().hex}'
    buffer = io.BytesIO()
    Image.new('RGB', (24, 18), '#c6a15b').save(buffer, format='BMP')
    response = client.post(
        '/api/v1/admin/products/save',
        headers=headers,
        data={'payload': json.dumps(_product_payload(ref))},
        files={'image': ('legacy.bmp', buffer.getvalue(), 'image/bmp')},
    )
    assert response.status_code == 201
    product_data = response.json()['product']
    assert product_data['imageUrl'].endswith('.webp')
    with SessionLocal() as db:
        product = db.scalar(select(Product).where(Product.ref == ref))
        assert product is not None
        assert product.image_mime_type == 'image/webp'
        image_path = get_settings().media_root / product.image_path
        assert image_path.read_bytes().startswith(b'RIFF')
    image_path.unlink(missing_ok=True)


def test_admin_can_delete_unused_product(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'delete-{uuid4().hex}'
    assert client.post('/api/v1/admin/products', headers=headers, json=_product_payload(ref)).status_code == 201
    response = client.delete(f'/api/v1/admin/products/{ref}', headers=headers)
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.get(Product, ref) is None


def test_admin_can_delete_order(client):
    login, user_id = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        order = Order(
            public_number=identifier,
            request_id=f'request-{uuid4().hex}',
            user_id=user_id,
            created_by_user_id=user_id,
            customer_name='Cliente de teste',
            subtotal=Decimal('0.00'), total=Decimal('0.00'), units=0, lines=0,
        )
        db.add(order)
        db.commit()
    response = client.delete(f'/api/v1/admin/orders/{identifier}', headers=headers)
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(Order).filter(Order.public_number == identifier).first() is None
