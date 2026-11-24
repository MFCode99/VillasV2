from __future__ import annotations

from collections.abc import Iterable

from .models import User


DEFAULT_CATALOGS = ('villas', 'interpilhas')


def normalize_catalog_access(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        slug = str(value or '').strip().casefold()
        if slug and slug not in result:
            result.append(slug)
    return result


def user_catalog_access(user: User | None) -> list[str]:
    if user is None:
        return []
    metadata = dict(user.metadata_json or {})
    if 'catalog_access' in metadata:
        return normalize_catalog_access(metadata.get('catalog_access'))
    if user.role in {'admin', 'developer'}:
        return list(DEFAULT_CATALOGS)
    return ['villas']


def set_user_catalog_access(user: User, values: Iterable[str] | None) -> list[str]:
    normalized = normalize_catalog_access(values)
    metadata = dict(user.metadata_json or {})
    metadata['catalog_access'] = normalized
    user.metadata_json = metadata
    return normalized


def can_access_catalog(user: User | None, catalog_slug: str | None) -> bool:
    if user is not None and user.role in {'admin', 'developer'}:
        return True
    return str(catalog_slug or '').strip().casefold() in user_catalog_access(user)
