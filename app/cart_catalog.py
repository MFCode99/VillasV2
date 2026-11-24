from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from fastapi import HTTPException, status

from .catalog import normalize_reference


CATALOG_MINIMUM_TOTALS = {
    'villas': Decimal('250.00'),
    'interpilhas': Decimal('300.00'),
}


def normalize_cart_catalog(value: str | None) -> str:
    catalog_slug = normalize_reference(value).casefold() or 'villas'
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', catalog_slug):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='catalog_not_found')
    return catalog_slug


def cart_item_catalog(item: Any) -> str:
    product = getattr(item, 'product', None)
    if product is not None and getattr(product, 'catalog_slug', None):
        return normalize_cart_catalog(product.catalog_slug)
    snapshot = dict(getattr(item, 'product_snapshot', None) or {})
    return normalize_cart_catalog(snapshot.get('catalog_slug'))


def catalog_revision(cart: Any, catalog_slug: str) -> int:
    catalog_slug = normalize_cart_catalog(catalog_slug)
    revisions = dict(getattr(cart, 'catalog_revisions_json', None) or {})
    if catalog_slug in revisions:
        return int(revisions[catalog_slug] or 0)
    if revisions:
        return 0
    return int(getattr(cart, 'revision', 0) or 0)


def increment_catalog_revision(cart: Any, catalog_slug: str) -> int:
    catalog_slug = normalize_cart_catalog(catalog_slug)
    base_revision = int(getattr(cart, 'revision', 0) or 0)
    revisions = dict(getattr(cart, 'catalog_revisions_json', None) or {})
    revisions.setdefault(catalog_slug, 0 if revisions else base_revision)
    revisions[catalog_slug] = int(revisions[catalog_slug] or 0) + 1
    cart.catalog_revisions_json = revisions
    # Keep the legacy column moving forward for diagnostics and old code paths.
    cart.revision = max(int(value or 0) for value in revisions.values())
    return int(revisions[catalog_slug])


def minimum_total_for_catalog(catalog_slug: str, db: Any | None = None) -> Decimal:
    catalog_slug = normalize_cart_catalog(catalog_slug)
    if db is not None:
        from .models import Catalog
        catalog = db.get(Catalog, catalog_slug)
        if catalog is not None and catalog.minimum_total is not None:
            configured = Decimal(str(catalog.minimum_total))
            if configured > 0 or catalog_slug not in CATALOG_MINIMUM_TOTALS:
                return configured
    return CATALOG_MINIMUM_TOTALS.get(catalog_slug, Decimal('0.00'))
