from io import BytesIO
from uuid import uuid4

from openpyxl import Workbook

from app.db import SessionLocal
from app.models import Catalog, Category, Product
from app.services import UserAdminService


def _login_admin(client):
    username = f'admin_{uuid4().hex}'
    with SessionLocal() as db:
        UserAdminService().create_user(db, username=username, password='secret123', full_name='Dynamic Catalog Admin', role='admin', active=True)
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': 'secret123'})
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrfToken']}


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'PRODUTOS'
    sheet.append(['Referência', 'Marca', 'Categoria', 'Subcategoria', 'Descrição', 'Preço Unitário', 'Múltiplo', 'Atalhos de quantidade'])
    sheet.append(['DYN-001', 'Marca', 'Consumíveis', 'Recargas', 'Produto dinâmico', '1,25', 2, '6, 12'])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_admin_creates_catalog_and_imports_full_excel_structure(client):
    headers = _login_admin(client)
    created = client.post('/api/v1/admin/catalogs', headers=headers, json={
        'label': 'Novo Catálogo', 'slug': 'novo-catalogo', 'description': 'Teste',
        'icon': 'mdi-bookshelf', 'minimum_total': '125.00', 'sort_order': 30, 'active': True,
    })
    assert created.status_code == 201
    assert created.json()['catalog']['minimumTotal'] == '125.00'

    preview = client.post('/api/v1/admin/import/products/preview', headers=headers, data={'catalog': 'novo-catalogo'}, files={'file': ('produtos.xlsx', _workbook(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert preview.status_code == 200
    payload = preview.json()
    assert payload['summary']['create'] == 1
    assert len(payload['categories']) == 2

    committed = client.post('/api/v1/admin/import/products/commit', headers=headers, json={'rows': [row['payload'] for row in payload['rows']], 'categories': payload['categories'], 'update_existing': True})
    assert committed.status_code == 200
    with SessionLocal() as db:
        product = db.get(Product, 'DYN-001')
        category = db.get(Category, product.category_slug)
        assert product.catalog_slug == 'novo-catalogo'
        assert category.label == 'Recargas'
        assert db.get(Category, category.parent_slug).label == 'Consumíveis'

    template = client.get('/api/v1/admin/import/products/template.xlsx')
    assert template.status_code == 200
    assert template.content.startswith(b'PK')


def test_statistics_keep_inactive_catalogs_and_support_annual_view(client):
    headers = _login_admin(client)
    created = client.post('/api/v1/admin/catalogs', headers=headers, json={
        'label': 'Catálogo Arquivado', 'slug': 'catalogo-arquivado', 'description': 'Histórico',
        'icon': 'mdi-archive-outline', 'minimum_total': '0.00', 'sort_order': 90, 'active': False,
    })
    assert created.status_code == 201

    monthly = client.get('/api/v1/admin/statistics', params={'scope': 'month', 'year': 2026, 'month': 1})
    assert monthly.status_code == 200
    inactive = next(row for row in monthly.json()['detail']['catalog_breakdown'] if row['slug'] == 'catalogo-arquivado')
    assert inactive['active'] is False
    assert float(inactive['revenue']) == 0.0

    annual = client.get('/api/v1/admin/statistics', params={'scope': 'year', 'year': 2026})
    assert annual.status_code == 200
    assert annual.json()['scope'] == 'year'
    assert len(annual.json()['detail']['months']) == 12

    exported = client.get('/admin/estatisticas/export.xlsx', params={'scope': 'year', 'year': 2026})
    assert exported.status_code == 200
    assert exported.content.startswith(b'PK')


def test_category_icons_and_confirmed_deletion_keep_products(client):
    headers = _login_admin(client)
    parent = client.post('/api/v1/admin/categories', headers=headers, json={
        'slug': 'material-escolar', 'catalog_slug': 'villas', 'parent_slug': None,
        'label': 'Material escolar', 'icon': 'mdi-school-outline', 'sort_order': 1, 'active': True,
    })
    assert parent.status_code == 200
    assert parent.json()['category']['icon'] == 'mdi-school-outline'
    child = client.post('/api/v1/admin/categories', headers=headers, json={
        'slug': 'cadernos', 'catalog_slug': 'villas', 'parent_slug': 'material-escolar',
        'label': 'Cadernos', 'icon': 'mdi-book-open-page-variant-outline', 'sort_order': 2, 'active': True,
    })
    assert child.status_code == 200
    with SessionLocal() as db:
        db.add(Product(ref='ICON-001', catalog_slug='villas', name='Caderno', product_type='Escolar', category_slug='cadernos', price=1, colors_json=[], sizes_json=[], active=True, manual_active=True, season='ambos', quantity_step=1, metadata_json={}))
        db.commit()

    deleted = client.delete('/api/v1/admin/categories/material-escolar', headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()['deletedChildren'] == 1
    assert deleted.json()['unassignedProducts'] == 1
    with SessionLocal() as db:
        assert db.get(Category, 'material-escolar') is None
        assert db.get(Category, 'cadernos') is None
        assert db.get(Product, 'ICON-001').category_slug is None


def test_custom_empty_catalog_can_be_deleted_but_system_catalogs_are_protected(client):
    headers = _login_admin(client)
    assert client.post('/api/v1/admin/catalogs', headers=headers, json={
        'label': 'Temporário', 'slug': 'temporario', 'description': '', 'icon': 'mdi-archive-outline',
        'minimum_total': '0.00', 'sort_order': 99, 'active': False,
    }).status_code == 201
    assert client.post('/api/v1/admin/categories', headers=headers, json={
        'slug': 'temporario-categoria', 'catalog_slug': 'temporario', 'parent_slug': None,
        'label': 'Temporária', 'icon': 'mdi-tag-outline', 'sort_order': 1, 'active': True,
    }).status_code == 200

    deleted = client.delete('/api/v1/admin/catalogs/temporario', headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()['deletedCategories'] == 1
    assert client.delete('/api/v1/admin/catalogs/villas', headers=headers).status_code == 409
    with SessionLocal() as db:
        assert db.get(Catalog, 'temporario') is None
        assert db.get(Category, 'temporario-categoria') is None
