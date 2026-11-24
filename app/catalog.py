from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from sqlalchemy.engine import make_url
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, aliased, selectinload

from .config import Settings
from .models import Catalog, Category, Product

MONEY_QUANT = Decimal('0.01')
VALID_SEASONS = {'ambos', 'inverno', 'verao'}


def normalize_text(value: str | None) -> str:
    return (value or '').strip()


def normalize_reference(value: str | None) -> str:
    return normalize_text(value)


def normalize_season(value: str | None) -> str:
    normalized = normalize_text(value).casefold()
    if normalized in {'ambos', 'both', 'all', 'all-season', 'three'}:
        return 'ambos'
    if normalized in {'inverno', 'winter'}:
        return 'inverno'
    if normalized in {'verao', 'summer'}:
        return 'verao'
    return 'ambos'


def normalize_qty_step(value: Any, default: int = 12) -> int:
    try:
        step = int(value)
    except (TypeError, ValueError):
        return default
    return step if step > 0 else default


def normalize_choice_text(value: Any) -> str:
    text = normalize_text(str(value) if value is not None else '')
    if not text:
        return ''
    text = text.strip()
    text = text.strip('[](){}')
    text = text.strip().strip('"').strip("'")
    text = text.strip('[](){}')
    return normalize_text(text)


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal:
    if value is None or value == '':
        if default is None:
            raise ValueError('decimal_value_required')
        return default
    if isinstance(value, Decimal):
        return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        if default is None:
            raise
        return default


def split_csv_values(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        try:
            decoded = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            decoded = None
        raw_items = decoded if isinstance(decoded, list) else text.split(',')
    else:
        raw_items = []
        for raw_item in value:
            if isinstance(raw_item, str) and ',' in raw_item:
                raw_items.extend(raw_item.split(','))
            else:
                raw_items.append(raw_item)
    items: list[str] = []
    for item in raw_items:
        text = normalize_choice_text(item)
        if text and text not in items:
            items.append(text)
    return items


def safe_filename_component(value: str | None) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', normalize_text(value))
    cleaned = cleaned.strip('_')
    return cleaned or 'product'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def product_fingerprint(
    *,
    ref: str,
    name: str,
    product_type: str,
    category_slug: str | None,
    price: Any,
    pvp: Any,
    colors: Iterable[str] | None,
    sizes: Iterable[str] | None,
    sort_order: int,
    active: bool,
    manual_active: bool,
    season: str,
    quantity_step: int,
    description: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        'ref': normalize_reference(ref),
        'name': normalize_text(name),
        'product_type': normalize_text(product_type),
        'category_slug': normalize_reference(category_slug),
        'price': f'{to_decimal(price):.2f}',
        'pvp': None if pvp in (None, '') else f'{to_decimal(pvp):.2f}',
        'colors': split_csv_values(colors),
        'sizes': split_csv_values(sizes),
        'sort_order': int(sort_order or 0),
        'active': bool(active),
        'manual_active': bool(manual_active),
        'season': normalize_season(season),
        'quantity_step': normalize_qty_step(quantity_step),
        'description': normalize_text(description) or None,
        'metadata': metadata or {},
    }
    return sha256_bytes(canonical_json(payload).encode('utf-8'))


@dataclass(slots=True)
class CatalogPage:
    items: list[Product]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        if not self.total:
            return 1
        return max(1, (self.total + self.per_page - 1) // self.per_page)


@dataclass(slots=True)
class ImportProductResult:
    ref: str
    status: str
    image_written: bool
    fingerprint: str
    image_checksum: str | None


@dataclass(slots=True)
class ImportSummary:
    categories_seen: int
    products_seen: int
    categories_created: int
    categories_updated: int
    products_created: int
    products_updated: int
    images_written: int
    dry_run: bool
    product_results: list[ImportProductResult]


@dataclass(slots=True)
class ValidationIssue:
    ref: str | None
    field: str
    expected: str
    actual: str
    severity: str = 'fail'


@dataclass(slots=True)
class ValidationSummary:
    source_products: int
    target_products: int
    source_categories: int
    target_categories: int
    matched_products: int
    matched_images: int
    issues: list[ValidationIssue]

    @property
    def passed(self) -> bool:
        return not self.issues


class CatalogService:
    def list_catalogs(self, db: Session, *, include_inactive: bool = False) -> list[Catalog]:
        stmt = select(Catalog).order_by(Catalog.sort_order.asc(), Catalog.label.asc())
        if not include_inactive:
            stmt = stmt.where(Catalog.active.is_(True))
        return list(db.execute(stmt).scalars().all())

    def list_categories(
        self,
        db: Session,
        *,
        catalog: str | None = None,
        include_inactive: bool = False,
    ) -> list[Category]:
        stmt = select(Category).order_by(Category.sort_order.asc(), Category.label.asc())
        if catalog:
            stmt = stmt.where(Category.catalog_slug == normalize_reference(catalog).casefold())
        if not include_inactive:
            stmt = stmt.where(Category.active.is_(True))
        items = list(db.execute(stmt).scalars().all())
        if include_inactive:
            return items
        active_slugs = {item.slug for item in items}
        return [item for item in items if item.parent_slug is None or item.parent_slug in active_slugs]

    def filter_options(self, db: Session, *, catalog: str) -> dict[str, list[str]]:
        catalog_value = normalize_reference(catalog).casefold() or 'villas'
        base = (Product.catalog_slug == catalog_value, Product.active.is_(True), Product.manual_active.is_(True), Product.gift_only.is_(False))
        brands = db.scalars(select(Product.brand).where(*base, Product.brand.is_not(None), Product.brand != '').distinct().order_by(Product.brand.asc())).all()
        families = db.scalars(select(Product.family).where(*base, Product.family.is_not(None), Product.family != '').distinct().order_by(Product.family.asc())).all()
        return {
            'brands': [str(value) for value in brands],
            'families': [str(value) for value in families],
        }

    def list_products(
        self,
        db: Session,
        *,
        q: str | None = None,
        ref: str | None = None,
        catalog: str | None = 'villas',
        category: str | None = None,
        subcategory: str | None = None,
        brand: str | None = None,
        family: str | None = None,
        season: str | None = None,
        sort: str | None = None,
        include_inactive: bool = False,
        page: int = 1,
        per_page: int = 24,
    ) -> CatalogPage:
        page = max(1, int(page or 1))
        per_page = max(1, min(int(per_page or 24), 5000 if include_inactive else 100))
        stmt = select(Product).options(selectinload(Product.catalog), selectinload(Product.category).selectinload(Category.parent))
        stmt = stmt.join(Category, Product.category_slug == Category.slug, isouter=True)
        catalog_value = normalize_reference(catalog).casefold() if catalog else ''
        if catalog_value:
            stmt = stmt.where(Product.catalog_slug == catalog_value)
        if subcategory:
            stmt = stmt.where(Product.category_slug == normalize_reference(subcategory))
        elif category:
            category_value = normalize_reference(category)
            child_slugs = list(db.scalars(select(Category.slug).where(Category.parent_slug == category_value)).all())
            stmt = stmt.where(Product.category_slug.in_([category_value, *child_slugs]))
        if brand:
            stmt = stmt.where(func.lower(Product.brand) == normalize_text(brand).casefold())
        if family:
            stmt = stmt.where(func.lower(Product.family) == normalize_text(family).casefold())
        if season:
            stmt = stmt.where(Product.season == normalize_season(season))
        if ref:
            ref_value = normalize_reference(ref)
            stmt = stmt.where(Product.ref == ref_value)
        if q:
            query = f"%{normalize_text(q)}%"
            stmt = stmt.where(
                or_(
                    Product.ref.ilike(query),
                    Product.name.ilike(query),
                    Product.product_type.ilike(query),
                    Product.brand.ilike(query),
                    Product.family.ilike(query),
                    Product.ean.ilike(query),
                )
            )
        if not include_inactive:
            stmt = stmt.where(Product.active.is_(True), Product.manual_active.is_(True), Product.gift_only.is_(False))
            ParentCategory = aliased(Category)
            valid_categories = (
                select(Category.slug)
                .outerjoin(ParentCategory, Category.parent_slug == ParentCategory.slug)
                .where(Category.active.is_(True), or_(Category.parent_slug.is_(None), ParentCategory.active.is_(True)))
            )
            stmt = stmt.where(or_(Product.category_slug.is_(None), Product.category_slug.in_(valid_categories)))
        total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        sort_value = (sort or 'ref_asc').strip().casefold()
        order_map = {
            'ref_asc': (Product.ref.asc(),),
            'ref_desc': (Product.ref.desc(),),
            'name_asc': (Product.name.asc(), Product.ref.asc()),
            'name_desc': (Product.name.desc(), Product.ref.asc()),
            'price_asc': (Product.price.asc(), Product.ref.asc()),
            'price_desc': (Product.price.desc(), Product.ref.asc()),
        }
        order_columns = order_map.get(sort_value, order_map['ref_asc'])
        stmt = stmt.order_by(
            func.coalesce(Category.sort_order, 9999).asc(),
            *order_columns,
        )
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        items = list(db.execute(stmt).scalars().all())
        return CatalogPage(items=items, total=total, page=page, per_page=per_page)

    def get_product(self, db: Session, ref: str, *, catalog: str | None = None) -> Product | None:
        stmt = select(Product).options(selectinload(Product.catalog), selectinload(Product.category).selectinload(Category.parent)).where(Product.ref == normalize_reference(ref))
        if catalog:
            stmt = stmt.where(Product.catalog_slug == normalize_reference(catalog).casefold())
        return db.scalar(stmt)

    def catalog_counts(self, db: Session, *, catalog: str | None = None) -> dict[str, int]:
        product_filters = []
        category_filters = []
        if catalog:
            catalog_value = normalize_reference(catalog).casefold()
            product_filters.append(Product.catalog_slug == catalog_value)
            category_filters.append(Category.catalog_slug == catalog_value)
        total_products = db.scalar(select(func.count(Product.ref)).where(*product_filters)) or 0
        active_products = db.scalar(
            select(func.count(Product.ref)).where(*product_filters, Product.active.is_(True), Product.manual_active.is_(True))
        ) or 0
        total_categories = db.scalar(select(func.count(Category.slug)).where(*category_filters)) or 0
        active_categories = db.scalar(select(func.count(Category.slug)).where(*category_filters, Category.active.is_(True))) or 0
        winter_products = db.scalar(select(func.count(Product.ref)).where(*product_filters, Product.season == 'inverno')) or 0
        summer_products = db.scalar(select(func.count(Product.ref)).where(*product_filters, Product.season == 'verao')) or 0
        all_season_products = db.scalar(select(func.count(Product.ref)).where(*product_filters, Product.season == 'ambos')) or 0
        step_1_products = db.scalar(select(func.count(Product.ref)).where(*product_filters, func.coalesce(Product.quantity_step, 12) == 1)) or 0
        step_12_products = db.scalar(select(func.count(Product.ref)).where(*product_filters, func.coalesce(Product.quantity_step, 12) == 12)) or 0
        return {
            'totalProducts': total_products,
            'activeProducts': active_products,
            'inactiveProducts': max(total_products - active_products, 0),
            'totalCategories': total_categories,
            'activeCategories': active_categories,
            'inactiveCategories': max(total_categories - active_categories, 0),
            'winterProducts': winter_products,
            'summerProducts': summer_products,
            'allSeasonProducts': all_season_products,
            'step1Products': step_1_products,
            'step12Products': step_12_products,
        }


def _source_engine(source_url: str) -> Engine:
    return create_engine(source_url, pool_pre_ping=True, future=True)


def _load_v1_catalog_via_node(source_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    url = make_url(source_url)
    node_modules = Path('/home/nunogouveia/villas/node_modules')
    mysql2 = node_modules / 'mysql2' / 'promise.js'
    if not mysql2.exists():
        raise RuntimeError('node_mysql2_not_available')
    script = r"""
const mysql = require('mysql2/promise');

(async () => {
  const url = JSON.parse(process.argv[1]);
  const pool = await mysql.createPool({
    host: url.host,
    port: url.port ? Number(url.port) : 3306,
    user: url.username || 'villas_user',
    password: url.password || '',
    database: (url.database || '').replace(/^\//, ''),
    waitForConnections: true,
    connectionLimit: 1,
    charset: 'utf8mb4',
  });
  const [categories] = await pool.query(
    'SELECT id, label, ordem, activo, criado_em, atualizado_em FROM categorias ORDER BY ordem, id'
  );
  const [products] = await pool.query(
    'SELECT ref, nome, tipo, cat, preco, pvp, cores, tams, imagem, ordem, activo, estacao, qtd_step, activo_manual, criado_em, atualizado_em FROM produtos ORDER BY ordem, ref'
  );
  console.log(JSON.stringify({categories, products}));
  await pool.end();
})().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
"""
    payload = {
        'host': url.host,
        'port': url.port,
        'username': url.username,
        'password': url.password,
        'database': url.database,
    }
    completed = subprocess.run(
        ['node', '-e', script, json.dumps(payload)],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(node_modules.parent),
    )
    data = json.loads(completed.stdout or '{}')
    return list(data.get('categories') or []), list(data.get('products') or [])


def _decode_data_url(image_value: str | None) -> tuple[bytes | None, str | None, str | None]:
    text = normalize_text(image_value)
    if not text:
        return None, None, None
    if not text.startswith('data:image/'):
        return None, None, None
    try:
        header, payload = text.split(',', 1)
        mime = header.split(';', 1)[0][5:].lower()
        ext = mimetypes.guess_extension(mime) or '.bin'
        if ext == '.jpe':
            ext = '.jpg'
        data = base64.b64decode(payload, validate=True)
        return data, mime, ext.lstrip('.')
    except Exception:
        return None, None, None


def _materialize_image(media_root: Path, ref: str, image_value: str | None, *, write: bool) -> tuple[str | None, str | None, str | None, bool]:
    data, mime, ext = _decode_data_url(image_value)
    if data is None or not mime or not ext:
        return None, None, None, False
    checksum = sha256_bytes(data)
    safe_ref = safe_filename_component(ref)
    relative_path = Path('products') / safe_ref / f'{checksum[:16]}.{ext}'
    absolute_path = media_root / relative_path
    wrote = False
    if write:
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        if not absolute_path.exists() or sha256_bytes(absolute_path.read_bytes()) != checksum:
            absolute_path.write_bytes(data)
            wrote = True
    return relative_path.as_posix(), checksum, mime, wrote




def load_v1_catalog(source_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        engine = _source_engine(source_url)
        with engine.connect() as conn:
            categories = list(conn.exec_driver_sql(
                'SELECT id, label, ordem, activo, criado_em, atualizado_em FROM categorias ORDER BY ordem, id'
            ).mappings())
            products = list(conn.exec_driver_sql(
                'SELECT ref, nome, tipo, cat, preco, pvp, cores, tams, imagem, ordem, activo, estacao, qtd_step, activo_manual, criado_em, atualizado_em FROM produtos ORDER BY ordem, ref'
            ).mappings())
        return categories, products
    except Exception as exc:
        source_text = str(source_url).lower()
        if 'sqlite' in source_text:
            raise
        node_modules = Path('/home/nunogouveia/villas/node_modules')
        if not node_modules.exists():
            raise
        categories, products = _load_v1_catalog_via_node(source_url)
        if categories or products:
            return categories, products
        raise exc


def import_v1_catalog(
    db: Session,
    *,
    source_url: str,
    media_root: Path,
    dry_run: bool = True,
) -> ImportSummary:
    source_categories, source_products = load_v1_catalog(source_url)
    categories_created = 0
    categories_updated = 0
    products_created = 0
    products_updated = 0
    images_written = 0
    product_results: list[ImportProductResult] = []

    existing_categories = {row.slug: row for row in db.execute(select(Category)).scalars().all()}
    for row in source_categories:
        slug = normalize_reference(row['id'])
        if not slug:
            continue
        attrs = {
            'slug': slug,
            'label': normalize_text(row.get('label')) or slug,
            'sort_order': int(row.get('ordem') or 0),
            'active': bool(row.get('activo', 1)),
            'visible_on_site': bool(row.get('activo', 1)),
        }
        category = existing_categories.get(slug)
        if category is None:
            category = Category(**attrs)
            if not dry_run:
                db.add(category)
            categories_created += 1
        else:
            category.label = attrs['label']
            category.sort_order = attrs['sort_order']
            category.active = attrs['active']
            category.visible_on_site = attrs['visible_on_site']
            categories_updated += 1

    category_slugs = {row['id'] for row in source_categories}
    existing_products = {row.ref: row for row in db.execute(select(Product)).scalars().all()}
    for row in source_products:
        ref = normalize_reference(row['ref'])
        if not ref:
            continue
        category_slug = normalize_reference(row.get('cat')) if row.get('cat') in category_slugs else None
        image_path, image_checksum, image_mime_type, wrote_image = _materialize_image(media_root, ref, row.get('imagem'), write=not dry_run)
        fingerprint = product_fingerprint(
            ref=ref,
            name=row.get('nome') or '',
            product_type=row.get('tipo') or '',
            category_slug=category_slug,
            price=row.get('preco'),
            pvp=row.get('pvp'),
            colors=row.get('cores') or [],
            sizes=row.get('tams') or [],
            sort_order=int(row.get('ordem') or 0),
            active=bool(row.get('activo', 1)),
            manual_active=bool(row.get('activo_manual', 1)),
            season=row.get('estacao') or 'ambos',
            quantity_step=row.get('qtd_step'),
            metadata={'source': 'v1'},
        )
        existing = existing_products.get(ref)
        if existing is None:
            existing = Product(ref=ref)
            if not dry_run:
                db.add(existing)
            products_created += 1
        else:
            products_updated += 1
        existing.name = normalize_text(row.get('nome')) or ref
        existing.product_type = normalize_text(row.get('tipo')) or 'Artigo'
        existing.category_slug = category_slug
        existing.price = to_decimal(row.get('preco'), Decimal('0.00'))
        existing.pvp = None if row.get('pvp') in (None, '') else to_decimal(row.get('pvp'))
        existing.colors_json = split_csv_values(row.get('cores') or [])
        existing.sizes_json = split_csv_values(row.get('tams') or [])
        existing.image_path = image_path
        existing.image_checksum = image_checksum
        existing.image_mime_type = image_mime_type
        existing.sort_order = int(row.get('ordem') or 0)
        existing.active = bool(row.get('activo', 1))
        existing.manual_active = bool(row.get('activo_manual', 1))
        existing.season = normalize_season(row.get('estacao'))
        existing.quantity_step = normalize_qty_step(row.get('qtd_step'), default=12)
        existing.description = existing.description
        existing.metadata_json = {
            'source': 'v1',
            'source_fingerprint': fingerprint,
            'source_category_label': row.get('cat'),
            'source_created_at': row.get('criado_em').isoformat() if isinstance(row.get('criado_em'), datetime) else None,
            'source_updated_at': row.get('atualizado_em').isoformat() if isinstance(row.get('atualizado_em'), datetime) else None,
        }
        if isinstance(row.get('criado_em'), datetime):
            existing.created_at = row['criado_em']
        if isinstance(row.get('atualizado_em'), datetime):
            existing.updated_at = row['atualizado_em']
        if wrote_image:
            images_written += 1
        product_results.append(
            ImportProductResult(
                ref=ref,
                status='created' if ref not in existing_products else 'updated',
                image_written=wrote_image,
                fingerprint=fingerprint,
                image_checksum=image_checksum,
            )
        )

    if not dry_run:
        db.commit()
    else:
        db.rollback()

    return ImportSummary(
        categories_seen=len(source_categories),
        products_seen=len(source_products),
        categories_created=categories_created,
        categories_updated=categories_updated,
        products_created=products_created,
        products_updated=products_updated,
        images_written=images_written,
        dry_run=dry_run,
        product_results=product_results,
    )


def validate_catalog_migration(
    *,
    source_url: str,
    target_db: Session,
    media_root: Path,
) -> ValidationSummary:
    source_categories, source_products = load_v1_catalog(source_url)
    target_categories = list(target_db.execute(select(Category).order_by(Category.sort_order.asc(), Category.slug.asc())).scalars().all())
    target_products = list(target_db.execute(select(Product).options(selectinload(Product.category)).order_by(Product.sort_order.asc(), Product.ref.asc())).scalars().all())

    issues: list[ValidationIssue] = []
    source_cat_map = {row['id']: row for row in source_categories}
    target_cat_map = {row.slug: row for row in target_categories}
    for slug, source in source_cat_map.items():
        target = target_cat_map.get(slug)
        if target is None:
            issues.append(ValidationIssue(ref=slug, field='category', expected='present', actual='missing'))
            continue
        if normalize_text(target.label) != normalize_text(source.get('label')):
            issues.append(ValidationIssue(ref=slug, field='category.label', expected=normalize_text(source.get('label')), actual=normalize_text(target.label)))
        if int(target.sort_order or 0) != int(source.get('ordem') or 0):
            issues.append(ValidationIssue(ref=slug, field='category.sort_order', expected=str(source.get('ordem') or 0), actual=str(target.sort_order or 0)))
        if bool(target.active) != bool(source.get('activo', 1)):
            issues.append(ValidationIssue(ref=slug, field='category.active', expected=str(bool(source.get('activo', 1))), actual=str(bool(target.active))))

    source_prod_map = {row['ref']: row for row in source_products}
    target_prod_map = {row.ref: row for row in target_products}
    matched_products = 0
    matched_images = 0
    for ref, source in source_prod_map.items():
        target = target_prod_map.get(ref)
        if target is None:
            issues.append(ValidationIssue(ref=ref, field='product', expected='present', actual='missing'))
            continue
        matched_products += 1
        expected_category = source.get('cat') if source.get('cat') in source_cat_map else None
        if normalize_reference(target.category_slug) != normalize_reference(expected_category):
            issues.append(ValidationIssue(ref=ref, field='category_slug', expected=str(expected_category), actual=str(target.category_slug)))
        if normalize_text(target.name) != normalize_text(source.get('nome')):
            issues.append(ValidationIssue(ref=ref, field='name', expected=normalize_text(source.get('nome')), actual=normalize_text(target.name)))
        if normalize_text(target.product_type) != normalize_text(source.get('tipo')):
            issues.append(ValidationIssue(ref=ref, field='product_type', expected=normalize_text(source.get('tipo')), actual=normalize_text(target.product_type)))
        if f'{to_decimal(target.price):.2f}' != f'{to_decimal(source.get("preco")):.2f}':
            issues.append(ValidationIssue(ref=ref, field='price', expected=f'{to_decimal(source.get("preco")):.2f}', actual=f'{to_decimal(target.price):.2f}'))
        source_pvp = None if source.get('pvp') in (None, '') else f'{to_decimal(source.get("pvp")):.2f}'
        target_pvp = None if target.pvp in (None, '') else f'{to_decimal(target.pvp):.2f}'
        if source_pvp != target_pvp:
            issues.append(ValidationIssue(ref=ref, field='pvp', expected=str(source_pvp), actual=str(target_pvp)))
        if split_csv_values(source.get('cores') or []) != split_csv_values(target.colors_json or []):
            issues.append(ValidationIssue(ref=ref, field='colors', expected=json.dumps(split_csv_values(source.get('cores') or []), ensure_ascii=False), actual=json.dumps(split_csv_values(target.colors_json or []), ensure_ascii=False)))
        if split_csv_values(source.get('tams') or []) != split_csv_values(target.sizes_json or []):
            issues.append(ValidationIssue(ref=ref, field='sizes', expected=json.dumps(split_csv_values(source.get('tams') or []), ensure_ascii=False), actual=json.dumps(split_csv_values(target.sizes_json or []), ensure_ascii=False)))
        if normalize_season(source.get('estacao')) != normalize_season(target.season):
            issues.append(ValidationIssue(ref=ref, field='season', expected=normalize_season(source.get('estacao')), actual=normalize_season(target.season)))
        if normalize_qty_step(source.get('qtd_step')) != normalize_qty_step(target.quantity_step):
            issues.append(ValidationIssue(ref=ref, field='quantity_step', expected=str(normalize_qty_step(source.get('qtd_step'))), actual=str(normalize_qty_step(target.quantity_step))))
        if bool(source.get('activo', 1)) != bool(target.active):
            issues.append(ValidationIssue(ref=ref, field='active', expected=str(bool(source.get('activo', 1))), actual=str(bool(target.active))))
        if bool(source.get('activo_manual', 1)) != bool(target.manual_active):
            issues.append(ValidationIssue(ref=ref, field='manual_active', expected=str(bool(source.get('activo_manual', 1))), actual=str(bool(target.manual_active))))
        source_data, _, _ = _decode_data_url(source.get('imagem'))
        if source_data is None:
            if target.image_path or target.image_checksum:
                issues.append(ValidationIssue(ref=ref, field='image', expected='empty', actual='present'))
            else:
                matched_images += 1
            continue
        expected_checksum = sha256_bytes(source_data)
        actual_checksum = target.image_checksum or ''
        if expected_checksum != actual_checksum:
            issues.append(ValidationIssue(ref=ref, field='image_checksum', expected=expected_checksum, actual=actual_checksum))
        if target.image_path:
            image_file = media_root / target.image_path
            if not image_file.exists():
                issues.append(ValidationIssue(ref=ref, field='image_file', expected='exists', actual='missing'))
            else:
                file_checksum = sha256_bytes(image_file.read_bytes())
                if file_checksum != expected_checksum:
                    issues.append(ValidationIssue(ref=ref, field='image_file_checksum', expected=expected_checksum, actual=file_checksum))
                else:
                    matched_images += 1
        else:
            issues.append(ValidationIssue(ref=ref, field='image_path', expected='present', actual='missing'))

    return ValidationSummary(
        source_products=len(source_products),
        target_products=len(target_products),
        source_categories=len(source_categories),
        target_categories=len(target_categories),
        matched_products=matched_products,
        matched_images=matched_images,
        issues=issues,
    )
