from __future__ import annotations

import base64
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table, Text, create_engine, insert
from sqlalchemy.orm import sessionmaker

from app.catalog import import_v1_catalog, validate_catalog_migration
from app.models import Base, Category, Product


PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        '89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6360000002000154A24F5D0000000049454E44AE426082'
    )
).decode('ascii')


def _make_target_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'target.sqlite3').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    return engine, SessionLocal()


def _make_source_db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'source.sqlite3').as_posix()}", future=True)
    metadata = MetaData()
    categorias = Table(
        'categorias',
        metadata,
        Column('id', String(80), primary_key=True),
        Column('label', String(120), nullable=False),
        Column('ordem', Integer, default=0),
        Column('activo', Integer, default=1),
        Column('criado_em', DateTime),
        Column('atualizado_em', DateTime),
    )
    produtos = Table(
        'produtos',
        metadata,
        Column('ref', String(30), primary_key=True),
        Column('nome', String(150), nullable=False),
        Column('tipo', String(120)),
        Column('cat', String(80), nullable=False),
        Column('preco', Numeric(10, 2), nullable=False),
        Column('pvp', Numeric(10, 2)),
        Column('cores', Text),
        Column('tams', Text),
        Column('imagem', Text),
        Column('ordem', Integer, default=0),
        Column('activo', Integer, default=1),
        Column('estacao', String(20), default='ambos'),
        Column('qtd_step', Integer, default=12),
        Column('activo_manual', Integer, default=1),
        Column('criado_em', DateTime),
        Column('atualizado_em', DateTime),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(categorias), [{'id': 'Soquetes', 'label': 'Soquetes', 'ordem': 0, 'activo': 1}])
        conn.execute(insert(produtos), [{
            'ref': '2145',
            'nome': 'Lycra Seda 15 DEN',
            'tipo': 'Mini Meia 2 Pares',
            'cat': 'Soquetes',
            'preco': Decimal('0.79'),
            'pvp': Decimal('1.95'),
            'cores': '["PRETO","MUSKADE"]',
            'tams': '["Unico"]',
            'imagem': f'data:image/png;base64,{PNG_1X1}',
            'ordem': 1,
            'activo': 1,
            'estacao': 'ambos',
            'qtd_step': 12,
            'activo_manual': 1,
        }])
    return engine


def test_v1_catalog_import_and_validation(tmp_path):
    source_engine = _make_source_db(tmp_path)
    target_engine, target_db = _make_target_session(tmp_path)
    media_root = tmp_path / 'media'
    media_root.mkdir()

    source_url = str(source_engine.url)

    dry_run = import_v1_catalog(target_db, source_url=source_url, media_root=media_root, dry_run=True)
    assert dry_run.products_seen == 1
    assert dry_run.images_written == 0
    assert not any(media_root.rglob('*.*'))

    result = import_v1_catalog(target_db, source_url=source_url, media_root=media_root, dry_run=False)
    assert result.products_created == 1
    assert result.images_written == 1

    validation = validate_catalog_migration(source_url=source_url, target_db=target_db, media_root=media_root)
    assert validation.passed
    assert validation.matched_products == 1
    assert validation.matched_images == 1

    second = import_v1_catalog(target_db, source_url=source_url, media_root=media_root, dry_run=False)
    assert second.products_created == 0
    assert second.products_updated == 1
