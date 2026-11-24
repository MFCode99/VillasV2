from app.catalog_access import set_user_catalog_access, user_catalog_access
from app.models import User


def _user(role: str, metadata: dict | None = None) -> User:
    return User(
        username=f'{role}-test',
        password_hash='unused',
        full_name='Catalog Test',
        role=role,
        active=True,
        metadata_json=metadata or {},
    )


def test_legacy_defaults_depend_on_role():
    assert user_catalog_access(_user('client')) == ['villas']
    assert user_catalog_access(_user('admin')) == ['villas', 'interpilhas']
    assert user_catalog_access(_user('developer')) == ['villas', 'interpilhas']


def test_explicit_catalog_access_is_respected_for_every_role():
    admin = _user('admin')
    developer = _user('developer')
    set_user_catalog_access(admin, [])
    set_user_catalog_access(developer, ['villas'])
    assert user_catalog_access(admin) == []
    assert user_catalog_access(developer) == ['villas']
