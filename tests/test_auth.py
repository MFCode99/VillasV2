from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import verify_password
from app.services import UserAdminService


def _create_user(*, username: str, password: str, role: str = 'client') -> None:
    with SessionLocal() as db:
        UserAdminService().create_user(
            db,
            username=username,
            password=password,
            full_name=f'{username} name',
            role=role,
            email=f'{username}@example.test',
            active=True,
        )


def test_login_redirects_by_role(client):
    username = f'admin_{uuid4().hex}'
    _create_user(username=username, password='secret123', role='admin')

    response = client.post('/entrar', data={'username': username, 'password': 'secret123'}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers['location'] == '/admin'
    assert response.cookies.get('villas_v2_session')
    assert response.cookies.get('villas_v2_csrf')


def test_logout_requires_csrf_after_login(client):
    username = f'client_{uuid4().hex}'
    _create_user(username=username, password='secret123', role='client')

    login_response = client.post('/entrar', data={'username': username, 'password': 'secret123'}, follow_redirects=False)
    assert login_response.status_code == 303
    csrf_token = client.cookies.get('villas_v2_csrf')

    logout_response = client.post('/logout', data={'csrf_token': csrf_token}, follow_redirects=False)
    assert logout_response.status_code == 303
    assert logout_response.headers['location'] == '/entrar'


def test_admin_can_create_user_with_csrf(client):
    admin_username = f'admin_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')

    login_response = client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)
    assert login_response.status_code == 303
    csrf_token = client.cookies.get('villas_v2_csrf')

    new_username = f'client_{uuid4().hex}'
    new_email = f'{new_username}@example.test'
    response = client.post(
        '/admin/users',
        data={
            'csrf_token': csrf_token,
            'username': new_username,
            'full_name': 'Created From Test',
            'password': 'secret123',
            'role': 'client',
            'email': new_email,
            'active': 'on',
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers['location'].startswith('/admin/users')
    with SessionLocal() as db:
        created = db.scalar(select(User).where(User.username == new_username))
        assert created is not None
        assert created.role == 'client'


def test_users_page_lists_legacy_developers_without_offering_the_role(client):
    admin_username = f'admin_{uuid4().hex}'
    client_username = f'client_{uuid4().hex}'
    developer_username = f'developer_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')
    _create_user(username=client_username, password='secret123', role='client')
    _create_user(username=developer_username, password='secret123', role='developer')
    client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)

    response = client.get('/admin/clientes')

    assert response.status_code == 200
    assert client_username in response.text
    assert admin_username in response.text
    assert developer_username in response.text
    assert '<option value="developer">' not in response.text


def test_admin_can_reset_user_password(client):
    admin_username = f'admin_{uuid4().hex}'
    target_username = f'client_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')
    _create_user(username=target_username, password='old-secret', role='client')
    client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)
    csrf_token = client.cookies.get('villas_v2_csrf')
    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.username == target_username))
        target_id = target.id

    response = client.post(
        f'/admin/users/{target_id}/password',
        data={'csrf_token': csrf_token, 'password': 'new-secret-123'},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with SessionLocal() as db:
        updated = db.get(User, target_id)
        assert verify_password(updated.password_hash, 'new-secret-123')


def test_users_can_share_an_email_address():
    first_username = f'client_{uuid4().hex}'
    second_username = f'client_{uuid4().hex}'
    shared_email = f'shared_{uuid4().hex}@example.test'
    service = UserAdminService()
    with SessionLocal() as db:
        first = service.create_user(db, username=first_username, password='secret123', full_name='First', email=shared_email)
        second = service.create_user(db, username=second_username, password='secret123', full_name='Second')
        service.update_user(db, second.id, email=shared_email)
        assert first.email == shared_email
        assert second.email == shared_email


def test_admin_can_delete_user_without_commercial_history(client):
    admin_username = f'admin_{uuid4().hex}'
    target_username = f'client_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')
    _create_user(username=target_username, password='secret123', role='client')
    client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)
    csrf_token = client.cookies.get('villas_v2_csrf')
    with SessionLocal() as db:
        target_id = db.scalar(select(User.id).where(User.username == target_username))

    response = client.post(
        f'/admin/users/{target_id}/delete',
        data={'csrf_token': csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers['location'] == '/admin/clientes?deleted=1'
    with SessionLocal() as db:
        assert db.get(User, target_id) is None


def test_admin_can_save_internal_user_notes():
    username = f'client_{uuid4().hex}'
    _create_user(username=username, password='secret123', role='client')
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        UserAdminService().update_user(db, user.id, admin_notes='Prefere contacto durante a manhã.')
        assert user.admin_notes == 'Prefere contacto durante a manhã.'


def test_admin_can_toggle_all_client_accounts(client):
    admin_username = f'admin_{uuid4().hex}'
    first_client = f'client_{uuid4().hex}'
    second_client = f'client_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')
    _create_user(username=first_client, password='secret123', role='client')
    _create_user(username=second_client, password='secret123', role='client')
    client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)
    csrf_token = client.cookies.get('villas_v2_csrf')

    response = client.post(
        '/admin/users/clients/toggle-all',
        data={'csrf_token': csrf_token, 'active': 'false'},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with SessionLocal() as db:
        clients = db.scalars(select(User).where(User.username.in_([first_client, second_client]))).all()
        admin = db.scalar(select(User).where(User.username == admin_username))
        assert all(not item.active for item in clients)
        assert admin.active is True


def test_form_error_requested_by_javascript_returns_json(client):
    admin_username = f'admin_{uuid4().hex}'
    existing_username = f'client_{uuid4().hex}'
    _create_user(username=admin_username, password='secret123', role='admin')
    _create_user(username=existing_username, password='secret123', role='client')
    client.post('/entrar', data={'username': admin_username, 'password': 'secret123'}, follow_redirects=False)
    csrf_token = client.cookies.get('villas_v2_csrf')

    response = client.post(
        '/admin/users',
        data={'csrf_token': csrf_token, 'username': existing_username, 'full_name': 'Duplicate', 'password': 'secret123'},
        headers={'Accept': 'application/json', 'X-Requested-With': 'fetch'},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert response.json()['detail'] == 'username_exists'
