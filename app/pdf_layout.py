from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .models import SiteSetting, User


PDF_LAYOUT_SETTING_KEYS = {
    'no_prices': 'pdf_layout_no_prices',
    'priced': 'pdf_layout_priced',
}

DEFAULT_NO_PRICE_LAYOUT: dict[str, Any] = {
    'showCustomer': True,
    'showContact': True,
    'showCarrier': True,
    'showProductName': True,
    'showSummary': True,
    'showCategories': True,
    'blankColumn': True,
    'fontSize': 'normal',
    'headerStyle': 'compact',
    'showDocumentHeading': False,
}

DEFAULT_PRICED_LAYOUT: dict[str, Any] = {
    'showCustomer': True,
    'showContact': True,
    'showCarrier': False,
    'showProductName': True,
    'showSummary': True,
    'showCategories': False,
    'blankColumn': False,
    'fontSize': 'normal',
    'headerStyle': 'full',
    'showDocumentHeading': True,
}

_BOOL_KEYS = {
    'showCustomer',
    'showContact',
    'showCarrier',
    'showProductName',
    'showSummary',
    'showCategories',
    'blankColumn',
    'showDocumentHeading',
}
_FONT_SIZES = {'compact', 'normal', 'large'}
_HEADER_STYLES = {'full', 'compact', 'hidden'}


def normalize_pdf_kind(kind: str | None) -> str:
    return 'priced' if str(kind or '').casefold() == 'priced' else 'no_prices'


def normalize_pdf_layout(value: Any = None, *, kind: str = 'no_prices') -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_PRICED_LAYOUT if normalize_pdf_kind(kind) == 'priced' else DEFAULT_NO_PRICE_LAYOUT)
    for key in _BOOL_KEYS:
        if key in source:
            result[key] = bool(source[key])
    font_size = str(source.get('fontSize') or '').strip().casefold()
    if font_size in _FONT_SIZES:
        result['fontSize'] = font_size
    header_style = str(source.get('headerStyle') or '').strip().casefold()
    if header_style in _HEADER_STYLES:
        result['headerStyle'] = header_style
    return result


def get_pdf_layout(db: Session, *, kind: str = 'no_prices', user_id: int | None = None) -> dict[str, Any]:
    normalized_kind = normalize_pdf_kind(kind)
    if user_id is not None:
        user = db.get(User, user_id)
        layouts = dict((user.metadata_json or {}).get('pdf_layouts') or {}) if user is not None else {}
        if normalized_kind in layouts:
            return normalize_pdf_layout(layouts[normalized_kind], kind=normalized_kind)
    setting = db.get(SiteSetting, PDF_LAYOUT_SETTING_KEYS[normalized_kind])
    if setting is None:
        return normalize_pdf_layout(kind=normalized_kind)
    try:
        return normalize_pdf_layout(json.loads(setting.value), kind=normalized_kind)
    except (TypeError, ValueError, json.JSONDecodeError):
        return normalize_pdf_layout(kind=normalized_kind)


def save_pdf_layout(db: Session, value: Any, *, kind: str = 'no_prices') -> dict[str, Any]:
    normalized_kind = normalize_pdf_kind(kind)
    layout = normalize_pdf_layout(value, kind=normalized_kind)
    setting_key = PDF_LAYOUT_SETTING_KEYS[normalized_kind]
    setting = db.get(SiteSetting, setting_key)
    serialized = json.dumps(layout, ensure_ascii=False, separators=(',', ':'))
    if setting is None:
        setting = SiteSetting(key=setting_key, value=serialized)
        db.add(setting)
    else:
        setting.value = serialized
    db.commit()
    return layout


def has_user_pdf_layout(db: Session, user_id: int, *, kind: str = 'no_prices') -> bool:
    user = db.get(User, user_id)
    if user is None:
        return False
    return normalize_pdf_kind(kind) in dict((user.metadata_json or {}).get('pdf_layouts') or {})


def save_user_pdf_layout(db: Session, user_id: int, value: Any, *, kind: str = 'no_prices') -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError('user_not_found')
    normalized_kind = normalize_pdf_kind(kind)
    layout = normalize_pdf_layout(value, kind=normalized_kind)
    metadata = dict(user.metadata_json or {})
    layouts = dict(metadata.get('pdf_layouts') or {})
    layouts[normalized_kind] = layout
    metadata['pdf_layouts'] = layouts
    user.metadata_json = metadata
    db.commit()
    return layout


def reset_user_pdf_layout(db: Session, user_id: int, *, kind: str = 'no_prices') -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError('user_not_found')
    normalized_kind = normalize_pdf_kind(kind)
    metadata = dict(user.metadata_json or {})
    layouts = dict(metadata.get('pdf_layouts') or {})
    layouts.pop(normalized_kind, None)
    if layouts:
        metadata['pdf_layouts'] = layouts
    else:
        metadata.pop('pdf_layouts', None)
    user.metadata_json = metadata
    db.commit()
    return get_pdf_layout(db, kind=normalized_kind)
