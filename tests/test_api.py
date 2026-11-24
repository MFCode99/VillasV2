import io
import json
from types import SimpleNamespace
from decimal import Decimal
from uuid import uuid4

from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Cart, CartItem, Catalog, Category, GiftPromotionRedemption, Order, OrderLine, Product
from app.gift_promotions import qualifying_gifts
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
    assert client.get('/api/v1/email/status').status_code == 401


def test_client_cannot_read_email_status(client):
    _api_login(client)

    assert client.get('/api/v1/email/status').status_code == 403


def test_admin_system_health_reports_services_and_runtime(client, monkeypatch):
    _api_login(client, 'admin')
    monkeypatch.setattr('app.routes.api._smtp_health_snapshot', lambda **kwargs: {'ok': True, 'durationMs': 12.4, 'checkedAt': 1.0})

    assert client.get('/api/v1/email/status').status_code == 200

    response = client.get('/api/v1/admin/system-health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['database']['ok'] is True
    assert payload['email']['ok'] is True
    assert payload['storage']['pathsChecked'] == 3
    assert payload['runtime']['totalRequests'] >= 1
    assert payload['versions']['fastapi']


def test_admin_system_update_status_and_rejects_empty_apply(client, monkeypatch, tmp_path):
    monkeypatch.setattr('app.update_manager.get_settings', lambda: SimpleNamespace(update_dir=tmp_path))
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}

    response = client.get('/api/v1/admin/system-update')
    assert response.status_code == 200
    assert response.json()['updateAvailable'] is False

    apply_response = client.post('/api/v1/admin/system-update/apply', headers=headers)
    assert apply_response.status_code == 409
    assert apply_response.json()['detail'] == 'update_not_ready'


def test_admin_updates_page_supports_direct_navigation(client):
    response = client.get('/admin/gestao/atualizacoes')

    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']


def test_developer_appearance_page_supports_direct_navigation(client):
    response = client.get('/admin/developer/aparencia')

    assert response.status_code == 200
    assert '<div id="app"></div>' in response.text


def test_developer_configures_update_channel_and_admin_login_notice(client, monkeypatch, tmp_path):
    pending = tmp_path / 'pending'
    pending.mkdir()
    (pending / 'manifest.json').write_text(json.dumps({'version': '2099.1', 'notes': ['Teste']}), encoding='utf-8')
    (pending / 'payload.tar.gz').write_bytes(b'package')
    monkeypatch.setattr('app.update_manager.get_settings', lambda: SimpleNamespace(update_dir=tmp_path))
    login, _ = _api_login(client, 'developer')
    headers = {'X-CSRF-Token': login['csrfToken']}

    status_response = client.get('/api/v1/admin/system-update')
    assert status_response.status_code == 200
    assert status_response.json()['canEditRelease'] is True
    assert status_response.json()['canInstall'] is True
    assert client.get('/api/v1/admin/users').status_code == 200
    assert client.get('/api/v1/admin/dashboard').status_code == 200
    updated = client.put('/api/v1/admin/system-update/metadata', headers=headers, json={'channel': 'beta', 'notify_admins_on_login': False})
    assert updated.status_code == 200
    assert updated.json()['pending']['channel'] == 'beta'
    assert updated.json()['pending']['notifyAdminsOnLogin'] is False


def test_developer_announces_selected_old_notes_and_tracks_admin_reading(client, monkeypatch, tmp_path):
    history = tmp_path / 'history'
    history.mkdir()
    (history / '2098.4.json').write_text(json.dumps({
        'version': '2098.4',
        'title': 'Versão antiga',
        'summary': 'Resumo histórico',
        'sections': [{'title': 'Produtos', 'items': ['Nova pesquisa visual', 'Correção de imagens']}],
    }), encoding='utf-8')
    monkeypatch.setattr('app.update_manager.get_settings', lambda: SimpleNamespace(update_dir=tmp_path))

    developer_login, _ = _api_login(client, 'developer')
    developer_headers = {'X-CSRF-Token': developer_login['csrfToken']}
    created = client.post('/api/v1/admin/system-update/announcements', headers=developer_headers, json={
        'version': '2098.4',
        'selected_notes': ['Correção de imagens'],
    })
    assert created.status_code == 201
    announcement_id = created.json()['announcementId']

    admin_login, admin_id = _api_login(client, 'admin')
    admin_headers = {'X-CSRF-Token': admin_login['csrfToken']}
    announcement = client.get('/api/v1/system-update/announcement').json()['announcement']
    assert announcement['id'] == announcement_id
    assert announcement['notes'] == [{'section': 'Produtos', 'text': 'Correção de imagens'}]
    assert client.post(f'/api/v1/system-update/announcements/{announcement_id}/viewed', headers=admin_headers).status_code == 200
    assert client.post(f'/api/v1/system-update/announcements/{announcement_id}/acknowledged', headers=admin_headers).status_code == 200
    assert client.get('/api/v1/system-update/announcement').json()['announcement'] is None

    ignored_login, ignored_admin_id = _api_login(client, 'admin')
    ignored_headers = {'X-CSRF-Token': ignored_login['csrfToken']}
    assert client.get('/api/v1/system-update/announcement').json()['announcement']['id'] == announcement_id
    assert client.post(f'/api/v1/system-update/announcements/{announcement_id}/viewed', headers=ignored_headers).status_code == 200
    assert client.post(f'/api/v1/system-update/announcements/{announcement_id}/ignored', headers=ignored_headers).status_code == 200

    developer_login, _ = _api_login(client, 'developer')
    center = client.get('/api/v1/admin/system-update/announcement-center')
    assert center.status_code == 200
    row = center.json()['announcements'][0]
    recipient = next(item for item in row['recipients'] if item['id'] == admin_id)
    ignored_recipient = next(item for item in row['recipients'] if item['id'] == ignored_admin_id)
    assert row['viewedCount'] >= 1
    assert row['acknowledgedCount'] >= 1
    assert recipient['status'] == 'acknowledged'
    assert ignored_recipient['status'] == 'ignored'
    assert row['ignoredCount'] >= 1


def test_api_admin_can_create_and_toggle_user(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    username = f'new_{uuid4().hex}'
    response = client.post('/api/v1/admin/users', headers=headers, json={
        'username': username,
        'password': 'secret123',
        'full_name': 'Novo Cliente',
        'email': 'compras@example.test',
        'additional_emails': ['contabilidade@example.test', 'armazem@example.test'],
        'address_line1': 'Rua Fiscal 10',
        'postal_code': '1000-100',
        'city': 'Lisboa',
        'country': 'Portugal',
        'delivery_same_as_billing': False,
        'delivery_address_line1': 'Rua do Armazém 20',
        'delivery_postal_code': '2000-200',
        'delivery_city': 'Santarém',
        'delivery_country': 'Portugal',
        'carrier': 'Transportadora Teste',
        'catalogs': ['villas', 'interpilhas'],
        'role': 'client',
        'active': True,
    })
    assert response.status_code == 201
    user = response.json()['user']
    assert user['carrier'] == 'Transportadora Teste'
    assert user['additionalEmails'] == ['contabilidade@example.test', 'armazem@example.test']
    assert user['deliverySameAsBilling'] is False
    assert user['deliveryAddressLine1'] == 'Rua do Armazém 20'
    assert user['deliveryCity'] == 'Santarém'
    assert user['catalogs'] == ['villas', 'interpilhas']
    access = client.post(f"/api/v1/admin/users/{user['id']}/share-access", headers=headers)
    assert access.status_code == 200
    assert access.json()['access']['username'] == username
    assert access.json()['access']['password']
    assert access.json()['access']['loginUrl'].endswith('/')
    catalogs = client.patch(f"/api/v1/admin/users/{user['id']}/catalogs", headers=headers, json={'catalogs': ['interpilhas']})
    assert catalogs.status_code == 200
    assert catalogs.json()['user']['catalogs'] == ['interpilhas']
    toggle = client.patch(f"/api/v1/admin/users/{user['id']}/active", headers=headers, json={'active': False})
    assert toggle.status_code == 200
    assert toggle.json()['user']['active'] is False


def test_admin_can_create_one_time_access_invite_for_a_specific_user(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    username = f'invite_{uuid4().hex}'
    created = client.post('/api/v1/admin/users', headers=headers, json={
        'username': username,
        'password': 'original123',
        'full_name': 'Cliente Convidado',
        'role': 'client',
        'active': True,
    })
    assert created.status_code == 201
    user_id = created.json()['user']['id']

    generated = client.post(f'/api/v1/admin/users/{user_id}/access-invite', headers=headers)
    assert generated.status_code == 200
    invite = generated.json()['invite']
    assert invite['username'] == username
    assert invite['expiresInSeconds'] == 3600
    assert '/convite?token=' in invite['url']
    token = invite['url'].split('token=', 1)[1]
    detail_before = client.get(f'/api/v1/admin/users/{user_id}')
    assert detail_before.status_code == 200
    assert detail_before.json()['accessInvite']['status'] == 'valid'

    inspected = client.post('/api/v1/access-invite/inspect', json={'token': token})
    assert inspected.status_code == 200
    assert inspected.json()['invite']['username'] == username

    accepted = client.post('/api/v1/access-invite/accept', json={
        'token': token,
        'password': 'nova-password-123',
        'password_confirmation': 'nova-password-123',
    })
    assert accepted.status_code == 200
    assert client.post('/api/v1/access-invite/inspect', json={'token': token}).status_code == 410
    detail_after = client.get(f'/api/v1/admin/users/{user_id}')
    assert detail_after.json()['accessInvite']['status'] == 'used'
    status_after = client.get(f'/api/v1/admin/users/{user_id}/access-invite-status')
    assert status_after.status_code == 200
    assert status_after.json()['accessInvite']['status'] == 'used'
    assert client.post('/api/v1/auth/login', json={'username': username, 'password': 'nova-password-123'}).status_code == 200


def test_new_access_invite_invalidates_previous_link(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    username, user_id = _user('client')
    first = client.post(f'/api/v1/admin/users/{user_id}/access-invite', headers=headers).json()['invite']['url'].split('token=', 1)[1]
    second = client.post(f'/api/v1/admin/users/{user_id}/access-invite', headers=headers).json()['invite']['url'].split('token=', 1)[1]
    assert client.post('/api/v1/access-invite/inspect', json={'token': first}).status_code == 410
    assert client.post('/api/v1/access-invite/inspect', json={'token': second}).status_code == 200


def test_admin_can_choose_access_invite_duration(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    _, user_id = _user('client')

    generated = client.post(
        f'/api/v1/admin/users/{user_id}/access-invite',
        headers=headers,
        json={'expires_in_hours': 72},
    )

    assert generated.status_code == 200
    assert generated.json()['invite']['expiresInSeconds'] == 72 * 3600
    assert client.post(
        f'/api/v1/admin/users/{user_id}/access-invite',
        headers=headers,
        json={'expires_in_hours': 721},
    ).status_code == 422


def test_client_catalog_access_is_enforced(client):
    username = f'catalog_{uuid4().hex}'
    with SessionLocal() as db:
        UserAdminService().create_user(
            db,
            username=username,
            password='secret123',
            full_name='Catalog Access',
            role='client',
            active=True,
            metadata_json={'catalog_access': ['interpilhas']},
        )
    login = client.post('/api/v1/auth/login', json={'username': username, 'password': 'secret123'})
    assert login.status_code == 200
    assert login.json()['user']['catalogs'] == ['interpilhas']
    assert client.get('/api/v1/catalog', params={'catalog': 'villas'}).status_code == 403
    allowed = client.get('/api/v1/catalog', params={'catalog': 'interpilhas'})
    assert allowed.status_code == 200
    assert [item['slug'] for item in allowed.json()['catalogs']] == ['interpilhas']
    navigation = client.get('/api/v1/catalog/navigation')
    assert navigation.status_code == 200
    assert [item['slug'] for item in navigation.json()['catalogs']] == ['interpilhas']
    assert navigation.json()['catalogs'][0]['label'] == 'Utilidades'


def test_catalog_navigation_returns_nested_active_categories(client):
    login, _ = _api_login(client, 'admin')
    assert client.get('/api/v1/catalog/navigation').status_code == 200
    parent_slug = f'parent-{uuid4().hex[:8]}'
    child_slug = f'child-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        db.add(Category(slug=parent_slug, catalog_slug='interpilhas', label='Grupo teste', sort_order=900, active=True, visible_on_site=True))
        db.add(Category(slug=child_slug, catalog_slug='interpilhas', parent_slug=parent_slug, label='Subgrupo teste', sort_order=901, active=True, visible_on_site=True))
        db.commit()

    response = client.get('/api/v1/catalog/navigation')
    assert response.status_code == 200
    catalog = next(item for item in response.json()['catalogs'] if item['slug'] == 'interpilhas')
    parent = next(item for item in catalog['categories'] if item['slug'] == parent_slug)
    assert [item['slug'] for item in parent['children']] == [child_slug]


def test_vue_history_routes_serve_built_app(client):
    index_response = client.get('/index.html')
    assert index_response.status_code == 200
    assert '<div id="app"></div>' in index_response.text
    response = client.get('/nova/admin/utilizadores')
    assert response.status_code == 200
    assert '<div id="app"></div>' in response.text
    cart_response = client.get('/carrinho/utilidades')
    assert cart_response.status_code == 200
    assert '<div id="app"></div>' in cart_response.text


def test_web_app_manifest_and_mobile_icon_are_served(client):
    manifest = client.get('/manifest.webmanifest')
    assert manifest.status_code == 200
    assert manifest.headers['content-type'].startswith('application/manifest+json')
    assert manifest.json()['name'] == 'Vitor Gouveia'
    assert manifest.json()['icons'][0]['src'] == '/icons/vitor-gouveia-app-192.png?v=20261114-2'
    assert manifest.headers['cache-control'] == 'public, max-age=300, must-revalidate'

    favicon = client.get('/static/assets/vitor-gouveia-favicon.png')
    assert favicon.status_code == 200
    assert favicon.headers['cache-control'] == 'public, max-age=604800, stale-while-revalidate=86400'

    icon = client.get('/icons/vitor-gouveia-app-192.png')
    assert icon.status_code == 200
    assert icon.headers['cache-control'] == 'public, max-age=2592000, immutable'

    worker = client.get('/sw.js')
    assert worker.status_code == 200
    assert worker.headers['content-type'].startswith('application/javascript')
    assert worker.headers['service-worker-allowed'] == '/'
    assert worker.headers['cache-control'] == 'no-store'

    ready = client.get('/ready')
    assert ready.headers['cache-control'] == 'no-store'
    icon = client.get('/icons/vitor-gouveia-apple-touch.png')
    assert icon.status_code == 200
    assert icon.headers['content-type'].startswith('image/png')
    favicon = client.get('/static/assets/vitor-gouveia-favicon.png')
    assert favicon.status_code == 200
    assert favicon.headers['content-type'].startswith('image/png')


def test_developer_can_configure_global_site_theme(client):
    initial = client.get('/api/v1/site/theme')
    assert initial.status_code == 200
    assert initial.json()['theme']['background'] == '#f7f5ef'

    admin_login, _ = _api_login(client, 'admin')
    payload = {
        'preset': 'ocean', 'adminCanView': True,
        'modeEnabled': True, 'mode': 'system', 'colorsEnabled': True,
        'densityEnabled': True, 'density': 'compact',
        'cornersEnabled': True, 'corners': 'rounded',
        'shadowsEnabled': True, 'shadows': 'normal',
        'textSizeEnabled': True, 'textSize': 'large',
        'contentWidthEnabled': True, 'contentWidth': 'wide',
        'motionEnabled': True, 'motion': 'subtle',
        'contrastEnabled': True, 'contrast': 'high',
        'tableStyleEnabled': True, 'tableStyle': 'striped',
        'primary': '#17324d', 'secondary': '#4f9b91', 'accent': '#4c78a8',
        'background': '#f3f7f6', 'surface': '#fcfefd',
        'darkPrimary': '#28557a', 'darkSecondary': '#65b7ad', 'darkAccent': '#79a4d0',
        'darkBackground': '#0d1923', 'darkSurface': '#152735',
    }
    assert client.get('/api/v1/admin/site/theme').status_code == 403
    assert client.put('/api/v1/admin/site/theme', json=payload, headers={'X-CSRF-Token': admin_login['csrfToken']}).status_code == 403

    developer_login, _ = _api_login(client, 'developer')
    updated = client.put('/api/v1/admin/site/theme', json=payload, headers={'X-CSRF-Token': developer_login['csrfToken']})
    assert updated.status_code == 200
    assert updated.json()['theme'] == payload
    assert client.get('/api/v1/site/theme').json()['theme'] == payload

    admin_login, _ = _api_login(client, 'admin')
    read_only = client.get('/api/v1/admin/site/theme')
    assert read_only.status_code == 200
    assert read_only.json() == {'theme': payload, 'canEdit': False}

    invalid = {**payload, 'primary': 'navy'}
    developer_login, _ = _api_login(client, 'developer')
    assert client.put('/api/v1/admin/site/theme', json=invalid, headers={'X-CSRF-Token': developer_login['csrfToken']}).status_code == 422


def test_user_can_choose_personal_theme_mode(client):
    login, _ = _api_login(client, 'client')
    headers = {'X-CSRF-Token': login['csrfToken']}

    updated = client.put('/api/v1/user/appearance', json={'mode': 'dark'}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()['mode'] == 'dark'
    assert client.get('/api/v1/session').json()['user']['appearanceMode'] == 'dark'

    invalid = client.put('/api/v1/user/appearance', json={'mode': 'sepia'}, headers=headers)
    assert invalid.status_code == 422


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


def test_admin_can_create_interpilhas_hierarchy_and_filter_catalog(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    parent = f'interpilhas-pilhas-{uuid4().hex[:8]}'
    child = f'{parent}-litio'
    assert client.post('/api/v1/admin/categories', headers=headers, json={
        'slug': parent,
        'catalog_slug': 'interpilhas',
        'parent_slug': None,
        'label': 'Pilhas',
        'sort_order': 1,
        'active': True,
    }).status_code == 200
    assert client.post('/api/v1/admin/categories', headers=headers, json={
        'slug': child,
        'catalog_slug': 'interpilhas',
        'parent_slug': parent,
        'label': 'Lítio',
        'sort_order': 2,
        'active': True,
    }).status_code == 200

    ref = f'INT-{uuid4().hex[:8]}'
    payload = _product_payload(ref) | {
        'catalog_slug': 'interpilhas',
        'category_slug': child,
        'brand': 'VARTA',
        'family': 'Lítio',
        'ean': '4008496276882',
        'price': '1.05',
        'price_base': '1.000',
        'eco_value': '0.049',
        'case_inner': 10,
        'case_outer': 100,
    }
    assert client.post('/api/v1/admin/products', headers=headers, json=payload).status_code == 201

    response = client.get('/api/v1/catalog', params={
        'catalog': 'interpilhas',
        'category': parent,
        'brand': 'VARTA',
        'family': 'Lítio',
    })
    assert response.status_code == 200
    result = response.json()
    assert result['catalog']['slug'] == 'interpilhas'
    assert result['total'] == 1
    assert result['items'][0]['ref'] == ref
    assert result['items'][0]['priceBase'] == '1.000'
    assert result['items'][0]['ecoValue'] == '0.049'


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


def test_admin_can_update_order_internal_notes(client):
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
    response = client.patch(f'/api/v1/admin/orders/{identifier}/notes', headers=headers, json={'notes': 'Nota só para admin'})
    assert response.status_code == 200
    assert response.json()['order']['internalNotes'] == 'Nota só para admin'
    with SessionLocal() as db:
        stored = db.query(Order).filter(Order.public_number == identifier).first()
        assert stored is not None
        assert stored.notes == 'Nota só para admin'


def test_admin_can_include_separate_observations_in_order_pdfs(client):
    login, user_id = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        db.add(Order(
            public_number=identifier,
            request_id=f'request-{uuid4().hex}',
            user_id=user_id,
            created_by_user_id=user_id,
            customer_name='Cliente PDF',
            subtotal=Decimal('0.00'), total=Decimal('0.00'), units=0, lines=0,
        ))
        db.commit()

    updated = client.patch(
        f'/api/v1/admin/orders/{identifier}/pdf-notes',
        headers=headers,
        json={'notes': 'Entregar apenas durante a manhã', 'include': True},
    )
    assert updated.status_code == 200
    assert updated.json()['order']['includePdfNotes'] is True
    assert updated.json()['order']['internalNotes'] == ''

    response = client.get(f'/api/v1/orders/{identifier}/pdf')
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(response.content)).pages)
    assert 'OBSERVAÇÕES' in text
    assert 'Entregar apenas durante a manhã' in text


def test_admin_manages_campaigns_and_active_home_filters_dates(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'CAMP-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
            db.flush()
        db.add(Product(
            ref=ref, catalog_slug='villas', name='Produto em campanha', product_type='Teste',
            price=Decimal('10.00'), colors_json=[], sizes_json=[], active=True, manual_active=True,
            season='ambos', quantity_step=1, metadata_json={},
        ))
        db.commit()

    created = client.post('/api/v1/admin/campaigns', headers=headers, json={
        'title': 'Campanha de teste', 'description': 'Seleção especial', 'active': True,
        'product_refs': [ref], 'sort_order': 1, 'show_text': False,
    })
    assert created.status_code == 201
    campaign = created.json()['campaign']
    assert campaign['currentlyActive'] is True
    assert campaign['productRefs'] == [ref]
    assert campaign['showText'] is False

    active = client.get('/api/v1/campaigns/active')
    assert active.status_code == 200
    assert active.json()['campaigns'][0]['products'][0]['ref'] == ref

    ended = client.put(f"/api/v1/admin/campaigns/{campaign['id']}", headers=headers, json={
        'title': 'Campanha de teste', 'active': True, 'product_refs': [ref],
        'starts_at': '2025-01-01T00:00:00', 'ends_at': '2025-01-02T00:00:00',
    })
    assert ended.status_code == 200
    assert client.get('/api/v1/campaigns/active').json()['campaigns'] == []


def test_campaign_image_and_customer_group_visibility(client):
    member_username, member_id = _user('client')
    outsider_username, _ = _user('client')
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    ref = f'CAMP-GROUP-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
            db.flush()
        db.add(Product(ref=ref, catalog_slug='villas', name='Produto segmentado', product_type='Teste', price=Decimal('10.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}))
        db.commit()

    group = client.post('/api/v1/admin/customer-groups', headers=headers, json={'name': 'Clientes especiais', 'description': 'Segmento de teste', 'active': True, 'user_ids': [member_id]})
    assert group.status_code == 201
    group_id = group.json()['group']['id']
    created = client.post('/api/v1/admin/campaigns', headers=headers, json={
        'title': 'Campanha segmentada', 'active': True, 'product_refs': [ref], 'group_ids': [group_id],
        'discount_type': 'percentage', 'discount_value': '20',
    })
    assert created.status_code == 201
    campaign_id = created.json()['campaign']['id']

    buffer = io.BytesIO()
    Image.new('RGB', (320, 140), '#17243d').save(buffer, format='JPEG')
    uploaded = client.post(f'/api/v1/admin/campaigns/{campaign_id}/image', headers=headers, data={'convert_to_png': 'true'}, files={'image': ('campanha.jpg', buffer.getvalue(), 'image/jpeg')})
    assert uploaded.status_code == 200
    image_path = get_settings().media_root / uploaded.json()['imageUrl'].removeprefix('/media/')
    assert image_path.is_file()
    assert image_path.suffix == '.png'
    with Image.open(image_path) as converted_image:
        assert converted_image.format == 'PNG'
        assert converted_image.size == (1500, 500)
        assert all(abs(actual - expected) <= 2 for actual, expected in zip(converted_image.getpixel((0, 0))[:3], (23, 36, 61)))
    served_image = client.get(uploaded.json()['imageUrl'])
    assert served_image.status_code == 200
    assert served_image.headers['cache-control'] == 'public, max-age=31536000, immutable'

    member_login = client.post('/api/v1/auth/login', json={'username': member_username, 'password': 'secret123'})
    assert member_login.status_code == 200
    member_headers = {'X-CSRF-Token': member_login.json()['csrfToken']}
    member_campaigns = client.get('/api/v1/campaigns/active').json()['campaigns']
    assert member_campaigns[0]['id'] == campaign_id
    assert member_campaigns[0]['imageUrl'].startswith('/media/campaigns/')
    assert member_campaigns[0]['products'][0]['price'] == '8.00'
    promoted_product = client.get(f'/api/v1/catalog/villas/{ref}').json()['product']
    assert promoted_product['price'] == '8.00'
    assert promoted_product['originalPrice'] == '10.00'

    added = client.post('/me/cart/items', headers=member_headers, json={
        'catalog_slug': 'villas', 'idempotency_key': f'campaign-cart-{uuid4().hex}',
        'cart_revision': 0, 'ref': ref, 'color': '', 'size': '', 'quantity': 32,
    })
    assert added.status_code == 200
    assert added.json()['cart']['items'][0]['unit_price'] == '8.00'
    assert added.json()['cart']['items'][0]['line_total'] == '256.00'
    submitted = client.post('/me/orders', headers={**member_headers, 'Accept': 'application/json'}, json={
        'catalog_slug': 'villas', 'idempotency_key': f'campaign-order-{uuid4().hex}', 'cart_revision': 1,
    })
    assert submitted.status_code == 201
    with SessionLocal() as db:
        line = db.scalar(select(OrderLine).where(OrderLine.order_id == submitted.json()['order']['id']))
        assert line is not None
        assert line.unit_price == Decimal('8.000')
        assert line.snapshot_json['campaign_id'] == campaign_id

    assert client.post('/api/v1/auth/login', json={'username': outsider_username, 'password': 'secret123'}).status_code == 200
    assert client.get('/api/v1/campaigns/active').json()['campaigns'] == []
    outsider_product = client.get(f'/api/v1/catalog/villas/{ref}').json()['product']
    assert outsider_product['price'] == '10.00'
    assert outsider_product['promotion'] is None
    image_path.unlink(missing_ok=True)


def test_gift_promotion_is_added_once_and_hidden_from_client_catalog(client):
    client_username, client_id = _user('client')
    admin_login, _ = _api_login(client, 'admin')
    admin_headers = {'X-CSRF-Token': admin_login['csrfToken']}
    eligible_ref = f'QUALIFY-{uuid4().hex[:8]}'
    gift_ref = f'GIFT-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
            db.flush()
        db.add_all([
            Product(ref=eligible_ref, catalog_slug='villas', name='Produto elegível', product_type='Teste', price=Decimal('100.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
            Product(ref=gift_ref, catalog_slug='villas', name='Oferta secreta', product_type='Oferta', price=Decimal('5.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
        ])
        db.commit()

    created = client.post('/api/v1/admin/gift-promotions', headers=admin_headers, json={
        'title': 'Oferta única', 'catalog_slug': 'villas', 'condition_type': 'quantity',
        'threshold_quantity': 3, 'product_refs': [eligible_ref], 'gift_product_ref': gift_ref,
        'gift_quantity': 1, 'active': True,
    })
    assert created.status_code == 201
    promotion_id = created.json()['promotion']['id']

    login = client.post('/api/v1/auth/login', json={'username': client_username, 'password': 'secret123'}).json()
    headers = {'X-CSRF-Token': login['csrfToken'], 'Accept': 'application/json'}
    catalog = client.get('/api/v1/catalog', params={'catalog': 'villas', 'per_page': 100}).json()
    assert gift_ref not in {item['ref'] for item in catalog['items']}
    assert client.get(f'/api/v1/catalog/villas/{gift_ref}').status_code == 404

    added = client.post('/me/cart/items', headers=headers, json={'catalog_slug': 'villas', 'idempotency_key': f'gift-cart-{uuid4().hex}', 'cart_revision': 0, 'ref': eligible_ref, 'color': '', 'size': '', 'quantity': 3})
    assert added.status_code == 200
    gift_line = next(item for item in added.json()['cart']['items'] if item['is_gift'])
    assert gift_line['ref'] == gift_ref
    assert gift_line['line_total'] == '0.00'

    submitted = client.post('/me/orders', headers=headers, json={'catalog_slug': 'villas', 'idempotency_key': f'gift-order-{uuid4().hex}', 'cart_revision': 1})
    assert submitted.status_code == 201
    assert any(item['snapshot'].get('is_gift') for item in submitted.json()['order']['items'])
    with SessionLocal() as db:
        redemption = db.scalar(select(GiftPromotionRedemption).where(GiftPromotionRedemption.promotion_id == promotion_id, GiftPromotionRedemption.user_id == client_id))
        assert redemption is not None

    added_again = client.post('/me/cart/items', headers=headers, json={'catalog_slug': 'villas', 'idempotency_key': f'gift-cart-again-{uuid4().hex}', 'cart_revision': 2, 'ref': eligible_ref, 'color': '', 'size': '', 'quantity': 3})
    assert added_again.status_code == 200
    assert not any(item['is_gift'] for item in added_again.json()['cart']['items'])


def test_gift_promotion_can_use_dynamic_brands_and_multiple_redemptions(client):
    client_username, client_id = _user('client')
    admin_login, _ = _api_login(client, 'admin')
    admin_headers = {'X-CSRF-Token': admin_login['csrfToken']}
    eligible_ref = f'BRAND-{uuid4().hex[:8]}'
    gift_ref = f'BRAND-GIFT-{uuid4().hex[:8]}'
    brand = f'Marca {uuid4().hex[:6]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
            db.flush()
        db.add_all([
            Product(ref=eligible_ref, catalog_slug='villas', name='Produto da marca', product_type='Teste', brand=brand, price=Decimal('150.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
            Product(ref=gift_ref, catalog_slug='villas', name='Oferta por marca', product_type='Oferta', price=Decimal('5.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
        ])
        db.commit()

    created = client.post('/api/v1/admin/gift-promotions', headers=admin_headers, json={
        'title': 'Oferta dinâmica por marca', 'catalog_slug': 'villas',
        'eligibility_mode': 'brands', 'eligible_brands': [brand], 'product_refs': [],
        'condition_type': 'value', 'threshold_value': '300.00',
        'gift_product_ref': gift_ref, 'gift_quantity': 1,
        'max_redemptions_per_user': 2, 'active': True,
    })
    assert created.status_code == 201
    promotion = created.json()['promotion']
    assert promotion['eligibleBrands'] == [brand]
    assert promotion['maxRedemptionsPerUser'] == 2

    login = client.post('/api/v1/auth/login', json={'username': client_username, 'password': 'secret123'}).json()
    headers = {'X-CSRF-Token': login['csrfToken'], 'Accept': 'application/json'}
    for redemption_number, revision in enumerate((0, 2), start=1):
        added = client.post('/me/cart/items', headers=headers, json={
            'catalog_slug': 'villas', 'idempotency_key': f'brand-gift-cart-{uuid4().hex}',
            'cart_revision': revision, 'ref': eligible_ref, 'color': '', 'size': '', 'quantity': 2,
        })
        assert added.status_code == 200
        assert any(item['is_gift'] and item['ref'] == gift_ref for item in added.json()['cart']['items'])
        submitted = client.post('/me/orders', headers=headers, json={
            'catalog_slug': 'villas', 'idempotency_key': f'brand-gift-order-{uuid4().hex}',
            'cart_revision': revision + 1,
        })
        assert submitted.status_code == 201, redemption_number

    third = client.post('/me/cart/items', headers=headers, json={
        'catalog_slug': 'villas', 'idempotency_key': f'brand-gift-cart-{uuid4().hex}',
        'cart_revision': 4, 'ref': eligible_ref, 'color': '', 'size': '', 'quantity': 2,
    })
    assert third.status_code == 200
    assert not any(item['is_gift'] for item in third.json()['cart']['items'])
    with SessionLocal() as db:
        redemptions = list(db.scalars(select(GiftPromotionRedemption).where(
            GiftPromotionRedemption.promotion_id == promotion['id'],
            GiftPromotionRedemption.user_id == client_id,
        )).all())
        assert len(redemptions) == 2


def test_gift_promotion_uses_one_matching_tier_with_its_own_product(client):
    _client_username, client_id = _user('client')
    admin_login, _ = _api_login(client, 'admin')
    admin_headers = {'X-CSRF-Token': admin_login['csrfToken']}
    eligible_ref = f'TIER-{uuid4().hex[:8]}'
    first_gift_ref = f'TIER-GIFT-A-{uuid4().hex[:6]}'
    second_gift_ref = f'TIER-GIFT-B-{uuid4().hex[:6]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
            db.flush()
        db.add_all([
            Product(ref=eligible_ref, catalog_slug='villas', name='Produto elegível por valor', product_type='Teste', price=Decimal('10.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
            Product(ref=first_gift_ref, catalog_slug='villas', name='Oferta dos 90 aos 200', product_type='Oferta', price=Decimal('0.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
            Product(ref=second_gift_ref, catalog_slug='villas', name='Oferta a partir dos 200', product_type='Oferta', price=Decimal('0.00'), colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}),
        ])
        db.commit()

    created = client.post('/api/v1/admin/gift-promotions', headers=admin_headers, json={
        'title': 'Oferta por escalões', 'catalog_slug': 'villas', 'condition_type': 'value',
        'product_refs': [eligible_ref], 'active': True,
        'tiers': [
            {'minimum_threshold': '90', 'maximum_threshold': '200', 'gift_product_ref': first_gift_ref, 'gift_quantity': 1},
            {'minimum_threshold': '200', 'maximum_threshold': None, 'gift_product_ref': second_gift_ref, 'gift_quantity': 2},
        ],
    })
    assert created.status_code == 201
    promotion = created.json()['promotion']
    assert [tier['giftProductRef'] for tier in promotion['tiers']] == [first_gift_ref, second_gift_ref]

    with SessionLocal() as db:
        first_awards = qualifying_gifts(db, user_id=client_id, catalog_slug='villas', lines=[
            {'ref': eligible_ref, 'quantity': 10, 'line_total': '100.00'},
        ])
        assert [(award.product.ref, award.quantity) for award in first_awards] == [(first_gift_ref, 1)]
        second_awards = qualifying_gifts(db, user_id=client_id, catalog_slug='villas', lines=[
            {'ref': eligible_ref, 'quantity': 20, 'line_total': '200.00'},
        ])
        assert [(award.product.ref, award.quantity) for award in second_awards] == [(second_gift_ref, 2)]

    overlap = client.post('/api/v1/admin/gift-promotions', headers=admin_headers, json={
        'title': 'Escalões sobrepostos', 'catalog_slug': 'villas', 'condition_type': 'value',
        'product_refs': [eligible_ref], 'active': False,
        'tiers': [
            {'minimum_threshold': '90', 'maximum_threshold': '200', 'gift_product_ref': first_gift_ref, 'gift_quantity': 1},
            {'minimum_threshold': '150', 'maximum_threshold': None, 'gift_product_ref': second_gift_ref, 'gift_quantity': 1},
        ],
    })
    assert overlap.status_code == 400
    assert overlap.json()['detail'] == 'gift_promotion_tier_overlap'


def test_cloudflare_area_is_developer_only_and_never_returns_token(client, monkeypatch):
    destination_calls = []
    fake = SimpleNamespace(
        dashboard=lambda: {'connected': True, 'tokenConfigured': True, 'zoneName': 'vitorgouveia.com', 'records': [], 'email': None},
        save_token=lambda token: {'id': 'a' * 32, 'name': 'vitorgouveia.com', 'status': 'active'},
        create_destination=lambda email: destination_calls.append(email) or {'id': 'b' * 32, 'email': email, 'verified': False},
    )
    monkeypatch.setattr('app.routes.api.cloudflare_service', fake)
    monkeypatch.setattr('app.routes.api.settings.smtp_from', 'portal@example.test')
    _api_login(client, 'admin')
    assert client.get('/api/v1/admin/cloudflare').status_code == 403

    developer_login, _ = _api_login(client, 'developer')
    headers = {'X-CSRF-Token': developer_login['csrfToken']}
    dashboard = client.get('/api/v1/admin/cloudflare')
    assert dashboard.status_code == 200
    assert dashboard.json()['zoneName'] == 'vitorgouveia.com'
    token_value = 'private-token-' + uuid4().hex
    connected = client.put('/api/v1/admin/cloudflare/connection', headers=headers, json={'token': token_value})
    assert connected.status_code == 200
    assert token_value not in connected.text
    destination = client.post('/api/v1/admin/cloudflare/email/destinations/portal', headers=headers)
    assert destination.status_code == 201
    assert destination_calls == ['portal@example.test']
    assert 'portal@example.test' not in destination.text


def test_authenticated_user_can_open_order_pdf_through_api(client):
    login, user_id = _api_login(client, 'admin')
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        order = Order(
            public_number=identifier,
            request_id=f'request-{uuid4().hex}',
            user_id=user_id,
            created_by_user_id=user_id,
            customer_name='Cliente PDF',
            subtotal=Decimal('0.00'), total=Decimal('0.00'), units=0, lines=0,
        )
        db.add(order)
        db.commit()

    response = client.get(f'/api/v1/orders/{identifier}/pdf')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'].startswith('inline;')
    assert response.content.startswith(b'%PDF-')

    no_prices = client.get(f'/api/v1/orders/{identifier}/pdf?hide_prices=1')
    assert no_prices.status_code == 200
    assert no_prices.content.startswith(b'%PDF-')
    download = client.get(f'/api/v1/orders/{identifier}/pdf?download=1')
    assert download.status_code == 200
    assert download.headers['content-disposition'].startswith('attachment;')


def test_admin_can_edit_and_preview_both_pdf_layouts(client):
    login, user_id = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        db.add(Order(
            public_number=identifier,
            request_id=f'request-{uuid4().hex}',
            user_id=user_id,
            created_by_user_id=user_id,
            customer_name='Cliente editor PDF',
            subtotal=Decimal('0.00'), total=Decimal('0.00'), units=0, lines=0,
        ))
        db.commit()

    current = client.get('/api/v1/admin/pdf-layout')
    assert current.status_code == 200
    assert current.json()['layout']['fontSize'] == 'normal'
    assert current.json()['layout']['blankColumn'] is True

    layout = {
        **current.json()['layout'],
        'showContact': False,
        'showCarrier': False,
        'fontSize': 'large',
    }
    saved = client.put('/api/v1/admin/pdf-layout', headers=headers, json=layout)
    assert saved.status_code == 200
    assert saved.json()['layout']['showContact'] is False
    assert saved.json()['layout']['fontSize'] == 'large'

    preview = client.post(f'/api/v1/admin/orders/{identifier}/pdf-preview', headers=headers, json=layout)
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'application/pdf'
    assert preview.content.startswith(b'%PDF-')

    priced_current = client.get('/api/v1/admin/pdf-layout?kind=priced')
    assert priced_current.status_code == 200
    assert priced_current.json()['layout']['headerStyle'] == 'full'
    assert priced_current.json()['layout']['showDocumentHeading'] is True
    priced_layout = {**priced_current.json()['layout'], 'showCarrier': True, 'headerStyle': 'compact'}
    priced_saved = client.put('/api/v1/admin/pdf-layout?kind=priced', headers=headers, json=priced_layout)
    assert priced_saved.status_code == 200
    assert priced_saved.json()['layout']['showCarrier'] is True
    priced_preview = client.post(f'/api/v1/admin/orders/{identifier}/pdf-preview?kind=priced', headers=headers, json=priced_layout)
    assert priced_preview.status_code == 200
    assert priced_preview.content.startswith(b'%PDF-')


def test_customer_pdf_layout_inherits_global_and_can_be_personalized(client):
    login, _ = _api_login(client, 'admin')
    headers = {'X-CSRF-Token': login['csrfToken']}
    _, customer_id = _user('client')
    global_layout = client.get('/api/v1/admin/pdf-layout?kind=priced').json()['layout']

    inherited = client.get(f'/api/v1/admin/pdf-layout?kind=priced&user_id={customer_id}')
    assert inherited.status_code == 200
    assert inherited.json()['customized'] is False
    assert inherited.json()['layout'] == global_layout

    personalized = {**global_layout, 'fontSize': 'large', 'showCarrier': True}
    saved = client.put(f'/api/v1/admin/pdf-layout?kind=priced&user_id={customer_id}', headers=headers, json=personalized)
    assert saved.status_code == 200
    assert saved.json()['customized'] is True
    assert saved.json()['layout']['fontSize'] == 'large'

    current = client.get(f'/api/v1/admin/pdf-layout?kind=priced&user_id={customer_id}')
    assert current.json()['customized'] is True
    assert current.json()['layout']['showCarrier'] is True

    reset = client.delete(f'/api/v1/admin/pdf-layout?kind=priced&user_id={customer_id}', headers=headers)
    assert reset.status_code == 200
    assert reset.json()['customized'] is False
    assert reset.json()['layout'] == global_layout


def test_user_detail_exposes_pending_carts_and_pdf_archive(client):
    login, _ = _api_login(client, 'admin')
    _, customer_id = _user('client')
    ref = f'cart-{uuid4().hex[:10]}'
    identifier = f'VLS-2099-{uuid4().hex[:8]}'
    with SessionLocal() as db:
        if db.get(Catalog, 'villas') is None:
            db.add(Catalog(slug='villas', label='Villas', minimum_total=Decimal('250.00'), active=True))
        product = Product(
            ref=ref, catalog_slug='villas', name='Produto pensado', product_type='Teste', price=Decimal('25.00'),
            colors_json=[], sizes_json=[], season='ambos', quantity_step=1, active=True, manual_active=True,
        )
        cart = Cart(user_id=customer_id, revision=1, catalog_revisions_json={'villas': 1}, source_version='v2')
        cart.items.append(CartItem(
            cart_user_id=customer_id, product_ref=ref, color='', size='', quantity=4,
            unit_price_snapshot=Decimal('25.000'), line_total_snapshot=Decimal('100.00'),
            product_name_snapshot='Produto pensado', product_type_snapshot='Teste',
            product_snapshot={'catalog_slug': 'villas', 'quantity_step': 1},
        ))
        db.add_all([product, cart, Order(
            public_number=identifier, request_id=f'request-{uuid4().hex}', user_id=customer_id,
            created_by_user_id=customer_id, customer_name='Cliente atividade', subtotal=Decimal('100.00'),
            total=Decimal('100.00'), units=4, lines=1, snapshot_json={'catalog_slug': 'villas', 'catalog_label': 'Villas'},
        )])
        db.commit()

    detail = client.get(f'/api/v1/admin/users/{customer_id}')
    assert detail.status_code == 200
    activity = detail.json()['activity']
    assert activity['summary']['pendingCarts'] == 1
    assert activity['summary']['documents'] == 2
    assert activity['carts'][0]['catalogLabel'] == 'Villas'
    assert activity['carts'][0]['total'] == '100.00'
    assert activity['carts'][0]['missingToMinimum'] == '150.00'
    assert {document['kind'] for document in activity['documents']} == {'priced', 'no_prices'}
    assert all(document['publicNumber'] == identifier for document in activity['documents'])

    refreshed = client.get(f'/api/v1/admin/users/{customer_id}/commercial-activity')
    assert refreshed.status_code == 200
    assert refreshed.json()['activity']['summary']['pendingCarts'] == 1

    dashboard = client.get('/api/v1/admin/dashboard')
    assert dashboard.status_code == 200
    pending = dashboard.json()['pendingCartActivity']
    assert pending['summary'] == {
        'customers': 1,
        'carts': 1,
        'lines': 1,
        'units': 4,
        'value': '100.00',
    }
    assert pending['customers'][0]['userId'] == customer_id
    assert pending['customers'][0]['catalogs'][0]['catalogLabel'] == 'Villas'

    overview = client.get('/api/v1/admin/pending-carts')
    assert overview.status_code == 200
    assert overview.json()['summary']['customers'] == 1
    assert overview.json()['customers'][0]['total'] == '100.00'
