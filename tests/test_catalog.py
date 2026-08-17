from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.catalog import CatalogService, normalize_season, split_csv_values, to_decimal
from app.models import Base, Category, Product


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'catalog.sqlite3').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)()


def test_catalog_normalizers():
    assert normalize_season('Winter') == 'inverno'
    assert normalize_season('VERAO') == 'verao'
    assert split_csv_values([' PRETO ', 'PRETO', 'AZUL']) == ['PRETO', 'AZUL']
    assert split_csv_values('["PRETO","MARINHO"]') == ['PRETO', 'MARINHO']
    assert split_csv_values(['["PRETO"', '"MARINHO"]']) == ['PRETO', 'MARINHO']
    assert split_csv_values(['Preto,Terra']) == ['Preto', 'Terra']
    assert to_decimal('12.3') == Decimal('12.30')


def test_catalog_service_filters_and_counts(tmp_path):
    db = _session(tmp_path)
    db.add(Category(slug='Soquetes', label='Soquetes', sort_order=0, active=True, visible_on_site=True))
    db.add(Category(slug='MiniMeia', label='Mini Meia / Meia Liga', sort_order=1, active=False, visible_on_site=False))
    db.add(Product(
        ref='2145',
        name='Lycra Seda 15 DEN',
        product_type='Mini Meia 2 Pares',
        category_slug='Soquetes',
        price=Decimal('0.79'),
        pvp=Decimal('1.95'),
        colors_json=['PRETO', 'MUSKADE'],
        sizes_json=['Unico'],
        image_path=None,
        image_checksum=None,
        image_mime_type=None,
        sort_order=1,
        active=True,
        manual_active=True,
        season='ambos',
        quantity_step=12,
        description=None,
        metadata_json={},
    ))
    db.add(Product(
        ref='6969',
        name='Test',
        product_type='Test',
        category_slug='MiniMeia',
        price=Decimal('1.00'),
        pvp=None,
        colors_json=[],
        sizes_json=[],
        image_path=None,
        image_checksum=None,
        image_mime_type=None,
        sort_order=2,
        active=False,
        manual_active=True,
        season='inverno',
        quantity_step=124,
        description=None,
        metadata_json={},
    ))
    db.commit()

    service = CatalogService()
    counts = service.catalog_counts(db)
    assert counts['totalProducts'] == 2
    assert counts['activeProducts'] == 1
    assert counts['totalCategories'] == 2

    page = service.list_products(db, q='2145')
    assert page.total == 1
    assert page.items[0].ref == '2145'

    page = service.list_products(db, season='inverno')
    assert page.total == 0

    page = service.list_products(db, include_inactive=True, season='inverno')
    assert page.total == 1
    assert page.items[0].ref == '6969'
