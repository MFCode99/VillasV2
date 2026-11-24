#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.media import persist_prepared_image, safe_filename_component
from app.models import Catalog, Category, Product


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_3(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.001'))


def load_manifest(package_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = package_dir / 'manifest.json'
    if not manifest_path.is_file():
        raise ValueError(f'Missing manifest: {manifest_path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    products = list(manifest.get('products') or [])
    if manifest.get('catalog') != 'interpilhas':
        raise ValueError('The package is not an Interpilhas catalog.')
    if int(manifest.get('product_count') or 0) != len(products) or len(products) != 419:
        raise ValueError(f'Expected 419 products, found {len(products)}.')
    refs = [str(product.get('ref') or '').strip() for product in products]
    if not all(refs) or len(refs) != len(set(refs)):
        raise ValueError('Product references are empty or duplicated.')
    for product in products:
        image_path = package_dir / 'images' / str(product.get('image_file') or '')
        if not image_path.is_file():
            raise ValueError(f"Missing image for {product['ref']}: {image_path.name}")
        if checksum(image_path) != product.get('image_checksum'):
            raise ValueError(f"Image checksum mismatch for {product['ref']}.")
        with Image.open(image_path) as image:
            image.verify()
            if image.format != 'WEBP':
                raise ValueError(f"Unexpected image format for {product['ref']}.")
        if decimal_3(product['price_base']) + decimal_3(product['eco_value']) != decimal_3(product['price']):
            raise ValueError(f"Invalid price arithmetic for {product['ref']}.")
    return manifest, products


def import_catalog(
    *,
    package_dir: Path,
    database_url: str,
    media_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    _manifest, products = load_manifest(package_dir)
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    created_files: list[Path] = []
    created = 0
    updated = 0
    unchanged = 0

    with session_factory() as db:
        catalog = db.get(Catalog, 'interpilhas')
        if catalog is None:
            raise ValueError('Interpilhas catalog is missing. Apply the catalog migrations first.')
        category_slugs = {str(product['category_slug']) for product in products}
        categories = {
            category.slug: category
            for category in db.scalars(select(Category).where(Category.slug.in_(category_slugs))).all()
        }
        missing_categories = sorted(category_slugs - set(categories))
        if missing_categories:
            raise ValueError(f'Missing Interpilhas categories: {missing_categories}')
        wrong_categories = sorted(slug for slug, row in categories.items() if row.catalog_slug != 'interpilhas')
        if wrong_categories:
            raise ValueError(f'Categories belong to another catalog: {wrong_categories}')

        existing_rows = {
            product.ref: product
            for product in db.scalars(select(Product).where(Product.ref.in_([row['ref'] for row in products]))).all()
        }
        collisions = sorted(ref for ref, row in existing_rows.items() if row.catalog_slug != 'interpilhas')
        if collisions:
            raise ValueError(f'References already used outside Interpilhas: {collisions[:20]}')

        try:
            for row in products:
                ref = str(row['ref'])
                image_bytes = (package_dir / 'images' / row['image_file']).read_bytes()
                image_checksum = str(row['image_checksum'])
                relative = Path('products') / 'interpilhas' / safe_filename_component(ref) / f'{image_checksum[:16]}.webp'
                absolute_path = media_root / relative
                relative_path = relative.as_posix()
                mime = 'image/webp'
                target = existing_rows.get(ref)
                is_new = target is None
                if target is None:
                    target = Product(ref=ref)
                    db.add(target)

                before = None if is_new else (
                    target.name, target.category_slug, target.brand, target.family, target.ean,
                    target.price, target.price_base, target.eco_value, target.case_inner,
                    target.case_outer, target.image_checksum, target.active,
                )
                target.catalog_slug = 'interpilhas'
                target.name = str(row['name']).strip()
                target.product_type = str(row['product_type']).strip()
                target.category_slug = str(row['category_slug'])
                target.brand = str(row.get('brand') or '').strip() or None
                target.family = str(row.get('family') or '').strip() or None
                target.ean = str(row.get('ean') or '').strip() or None
                target.price = decimal_3(row['price'])
                target.price_base = decimal_3(row['price_base'])
                target.eco_value = decimal_3(row['eco_value'])
                target.pvp = None
                target.case_inner = row.get('case_inner')
                target.case_outer = row.get('case_outer')
                target.colors_json = []
                target.sizes_json = []
                target.image_path = relative_path
                target.image_checksum = image_checksum
                target.image_mime_type = mime
                target.sort_order = int(row.get('sort_order') or 0)
                target.active = True
                target.manual_active = True
                target.season = 'ambos'
                target.quantity_step = int(row.get('quantity_step') or 1)
                target.description = None
                target.metadata_json = {
                    'supplier': 'Interpilhas',
                    'source': 'Interpilhas.xlsx',
                    'source_brand': row.get('brand'),
                }
                after = (
                    target.name, target.category_slug, target.brand, target.family, target.ean,
                    target.price, target.price_base, target.eco_value, target.case_inner,
                    target.case_outer, target.image_checksum, target.active,
                )
                if is_new:
                    created += 1
                elif before == after:
                    unchanged += 1
                else:
                    updated += 1

                if not dry_run and persist_prepared_image(absolute_path, image_bytes, image_checksum):
                    created_files.append(absolute_path)

            db.flush()
            if dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            for path in created_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        finally:
            engine.dispose()

    return {
        'ok': True,
        'dry_run': dry_run,
        'products': len(products),
        'created': created,
        'updated': updated,
        'unchanged': unchanged,
        'images_written': 0 if dry_run else len(created_files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate and import an Interpilhas catalog package.')
    parser.add_argument('--package-dir', type=Path, required=True)
    parser.add_argument('--database-url')
    parser.add_argument('--media-root', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    load_env_file(ROOT / '.env')
    get_settings.cache_clear()
    settings = get_settings()
    result = import_catalog(
        package_dir=args.package_dir.resolve(),
        database_url=args.database_url or settings.database_url,
        media_root=(args.media_root or settings.media_root).resolve(),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
