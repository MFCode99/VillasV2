from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import secrets
import string
from time import monotonic, perf_counter
import unicodedata
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..admin_business import AdminOrderDraftService, AdminStatisticsService, WarningService
from ..access_invites import accept_access_invite, create_access_invite, get_access_invite
from ..catalog import CatalogService, normalize_qty_step, normalize_reference, normalize_season, split_csv_values, to_decimal
from ..cloudflare_service import CloudflareService, CloudflareServiceError
from ..cart_service import CartService
from ..catalog_access import can_access_catalog, set_user_catalog_access, user_catalog_access
from ..config import get_settings
from ..dependencies import get_db
from ..diagnostics import diagnostics
from ..email_service import EmailService
from ..models import AdminAuditLog, Campaign, CampaignCustomerGroup, CampaignProduct, Cart, CartItem, Catalog, Category, CustomerGroup, CustomerGroupMember, EmailDeliveryLog, GiftPromotion, GiftPromotionProduct, GiftPromotionRedemption, GiftPromotionTier, Order, OrderLine, OrderRequestId, Product, ProductImportBatch, Session as AppSession, SiteSetting, User, UserAccessInvite
from ..media import calculate_image_zoom, persist_prepared_image, prepare_campaign_image, prepare_product_image, save_uploaded_product_image
from ..order_service import OrderService
from ..pdf_layout import get_pdf_layout, has_user_pdf_layout, normalize_pdf_layout, reset_user_pdf_layout, save_pdf_layout, save_user_pdf_layout
from ..pdf_service import build_order_pdf
from ..pdf_product_import import parse_pdf_product_images
from ..product_import import _key as import_match_key, parse_product_file
from ..promotions import PromotionInfo, active_promotions, price_for_campaign
from ..services import AuthService, UserAdminService
from ..security import hash_password, utcnow, verify_password
from .. import update_announcements
from ..update_manager import start_update, update_status, update_pending_metadata

router = APIRouter(prefix='/api/v1', tags=['api-v1'])
settings = get_settings()
auth_service = AuthService(settings)
catalog_service = CatalogService()
cart_service = CartService()
order_service = OrderService()
user_service = UserAdminService()
stats_service = AdminStatisticsService()
warning_service = WarningService()
draft_service = AdminOrderDraftService()
cloudflare_service = CloudflareService(zone_name=settings.cloudflare_zone_name, token_file=settings.cloudflare_token_file)
_email_health_cache: dict[str, Any] = {'checkedAt': 0.0, 'ok': False, 'durationMs': None}
SITE_THEME_SETTING_KEY = 'appearance.theme'
DEFAULT_SITE_THEME = {
    'preset': 'classic',
    'adminCanView': False,
    'modeEnabled': True,
    'mode': 'light',
    'colorsEnabled': True,
    'densityEnabled': True,
    'density': 'comfortable',
    'cornersEnabled': True,
    'corners': 'soft',
    'shadowsEnabled': True,
    'shadows': 'subtle',
    'textSizeEnabled': True,
    'textSize': 'normal',
    'contentWidthEnabled': True,
    'contentWidth': 'standard',
    'motionEnabled': True,
    'motion': 'normal',
    'contrastEnabled': True,
    'contrast': 'standard',
    'tableStyleEnabled': True,
    'tableStyle': 'clean',
    'primary': '#17243d',
    'secondary': '#b58c42',
    'accent': '#5271a5',
    'background': '#f7f5ef',
    'surface': '#fffdf8',
    'darkPrimary': '#29466f',
    'darkSecondary': '#d2ad62',
    'darkAccent': '#7394c1',
    'darkBackground': '#0f1726',
    'darkSurface': '#172236',
}
THEME_COLOR_KEYS = ('primary', 'secondary', 'accent', 'background', 'surface', 'darkPrimary', 'darkSecondary', 'darkAccent', 'darkBackground', 'darkSurface')
THEME_BOOLEAN_KEYS = ('adminCanView', 'modeEnabled', 'colorsEnabled', 'densityEnabled', 'cornersEnabled', 'shadowsEnabled', 'textSizeEnabled', 'contentWidthEnabled', 'motionEnabled', 'contrastEnabled', 'tableStyleEnabled')
THEME_ENUMS = {
    'mode': {'light', 'dark', 'system'},
    'density': {'compact', 'comfortable', 'spacious'},
    'corners': {'square', 'soft', 'rounded'},
    'shadows': {'none', 'subtle', 'normal'},
    'textSize': {'small', 'normal', 'large'},
    'contentWidth': {'focused', 'standard', 'wide'},
    'motion': {'none', 'subtle', 'normal'},
    'contrast': {'standard', 'high'},
    'tableStyle': {'clean', 'lines', 'striped'},
}
THEME_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def _site_theme(db: Session) -> dict[str, Any]:
    setting = db.get(SiteSetting, SITE_THEME_SETTING_KEY)
    if setting is None:
        return dict(DEFAULT_SITE_THEME)
    try:
        stored = json.loads(setting.value)
    except (TypeError, ValueError):
        return dict(DEFAULT_SITE_THEME)
    result = dict(DEFAULT_SITE_THEME)
    if isinstance(stored, dict):
        preset = str(stored.get('preset') or '').strip().casefold()
        if preset:
            result['preset'] = preset[:40]
        for key in THEME_BOOLEAN_KEYS:
            if isinstance(stored.get(key), bool):
                result[key] = stored[key]
        for key, allowed in THEME_ENUMS.items():
            value = str(stored.get(key) or '').strip().casefold()
            if value in allowed:
                result[key] = value
        for key in THEME_COLOR_KEYS:
            value = str(stored.get(key) or '')
            if THEME_COLOR_RE.fullmatch(value):
                result[key] = value.lower()
    return result


def _smtp_health_snapshot(*, max_age_seconds: float = 60.0) -> dict[str, Any]:
    now = monotonic()
    if now - float(_email_health_cache['checkedAt']) < max_age_seconds:
        return dict(_email_health_cache)
    started = perf_counter()
    ok = EmailService().health_check()
    _email_health_cache.update({
        'checkedAt': now,
        'ok': ok,
        'durationMs': round((perf_counter() - started) * 1000, 1),
    })
    return dict(_email_health_cache)


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return 'unknown'


def _business_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(settings.business_timezone))
    except Exception:
        return datetime.now(UTC)


def _access_invite_status(db: Session, user_id: int) -> dict[str, Any] | None:
    invite = db.execute(
        select(UserAccessInvite)
        .where(UserAccessInvite.user_id == user_id)
        .order_by(UserAccessInvite.created_at.desc(), UserAccessInvite.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if invite is None:
        return None
    status_value = 'used' if invite.used_at is not None else ('expired' if invite.expires_at <= utcnow() else 'valid')
    return {
        'id': invite.id,
        'status': status_value,
        'createdAt': invite.created_at,
        'expiresAt': invite.expires_at,
        'usedAt': invite.used_at,
    }


def _user_commercial_activity(
    db: Session,
    user_id: int,
    *,
    catalogs: list[Catalog] | None = None,
    orders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalogs = catalogs if catalogs is not None else catalog_service.list_catalogs(db, include_inactive=True)
    orders = orders if orders is not None else order_service.list_client_orders(db, user_id=user_id)

    pending_carts: list[dict[str, Any]] = []
    for catalog in catalogs:
        cart = cart_service.get_cart(db, user_id, catalog.slug)
        if not cart['lines']:
            continue
        total = Decimal(str(cart['total']))
        minimum = Decimal(str(cart['minimum_total']))
        pending_carts.append({
            **cart,
            'catalogLabel': catalog.label,
            'catalogIcon': catalog.icon or 'mdi-bookshelf',
            'catalogActive': bool(catalog.active),
            'missingToMinimum': f'{max(Decimal("0.00"), minimum - total):.2f}',
            'minimumReached': total >= minimum,
        })

    order_ids = [int(order['id']) for order in orders]
    email_logs = []
    if order_ids:
        email_logs = list(db.execute(
            select(EmailDeliveryLog)
            .where(EmailDeliveryLog.related_order_id.in_(order_ids), EmailDeliveryLog.status == 'sent')
            .order_by(EmailDeliveryLog.created_at.desc(), EmailDeliveryLog.id.desc())
        ).scalars().all())

    last_sent: dict[tuple[int, str], EmailDeliveryLog] = {}
    for log in email_logs:
        if log.related_order_id is None:
            continue
        if log.template_name == 'order_pdf_priced':
            kinds = ('priced',)
        elif log.template_name == 'order_pdf_unpriced':
            kinds = ('no_prices',)
        elif str(log.template_name or '').startswith('order_'):
            kinds = ('priced', 'no_prices')
        else:
            continue
        for kind in kinds:
            last_sent.setdefault((int(log.related_order_id), kind), log)

    documents: list[dict[str, Any]] = []
    for order in orders:
        for kind, label, hide_prices in (
            ('priced', 'Com preços', False),
            ('no_prices', 'Sem preços', True),
        ):
            sent = last_sent.get((int(order['id']), kind))
            base_url = f"/api/v1/orders/{order['publicNumber']}/pdf"
            query = '?hide_prices=1' if hide_prices else ''
            download_query = f"{'&' if query else '?'}download=1"
            documents.append({
                'id': f"{order['id']}-{kind}",
                'orderId': order['id'],
                'publicNumber': order['publicNumber'],
                'kind': kind,
                'label': label,
                'catalogSlug': order.get('catalogSlug') or 'villas',
                'catalogLabel': order.get('catalogLabel') or 'Villas',
                'orderStatus': order['orderStatus'],
                'orderStatusLabel': order['orderStatusLabel'],
                'total': order['total'],
                'createdAt': order['createdAt'],
                'viewUrl': base_url + query,
                'downloadUrl': base_url + query + download_query,
                'lastSentAt': sent.created_at if sent else None,
                'lastRecipient': sent.recipient if sent else '',
            })

    order_value = sum((Decimal(str(order.get('total') or 0)) for order in orders), Decimal('0.00'))
    cart_value = sum((Decimal(str(cart['total'])) for cart in pending_carts), Decimal('0.00'))
    return {
        'summary': {
            'orders': len(orders),
            'orderValue': f'{order_value:.2f}',
            'pendingCarts': len(pending_carts),
            'pendingCartValue': f'{cart_value:.2f}',
            'documents': len(documents),
            'lastOrderAt': orders[0]['createdAt'] if orders else None,
        },
        'carts': pending_carts,
        'documents': documents,
    }


def _pending_cart_overview(db: Session) -> dict[str, Any]:
    catalogs = catalog_service.list_catalogs(db, include_inactive=True)
    carts = db.execute(
        select(Cart)
        .join(User, Cart.user_id == User.id)
        .options(
            selectinload(Cart.user),
            selectinload(Cart.items).selectinload(CartItem.product),
        )
        .where(User.role == 'client')
    ).unique().scalars().all()

    customers: list[dict[str, Any]] = []
    total_value = Decimal('0.00')
    total_units = 0
    total_lines = 0
    total_carts = 0

    for cart in carts:
        catalog_carts: list[dict[str, Any]] = []
        customer_value = Decimal('0.00')
        customer_units = 0
        customer_lines = 0
        for catalog in catalogs:
            serialized = cart_service._serialize_cart(cart, catalog.slug, db)
            if not serialized['lines']:
                continue
            value = Decimal(str(serialized['total']))
            minimum = Decimal(str(serialized['minimum_total']))
            catalog_carts.append({
                'catalogSlug': catalog.slug,
                'catalogLabel': catalog.label,
                'catalogIcon': catalog.icon or 'mdi-bookshelf',
                'catalogActive': bool(catalog.active),
                'lines': serialized['lines'],
                'units': serialized['units'],
                'total': serialized['total'],
                'minimumTotal': serialized['minimum_total'],
                'minimumReached': value >= minimum,
            })
            customer_value += value
            customer_units += int(serialized['units'])
            customer_lines += int(serialized['lines'])

        if not catalog_carts:
            continue
        total_carts += len(catalog_carts)
        total_value += customer_value
        total_units += customer_units
        total_lines += customer_lines
        customers.append({
            'userId': cart.user_id,
            'name': cart.user.full_name,
            'username': cart.user.username,
            'company': cart.user.company_name,
            'active': bool(cart.user.active),
            'updatedAt': cart.updated_at,
            'lines': customer_lines,
            'units': customer_units,
            'total': f'{customer_value:.2f}',
            'catalogs': catalog_carts,
        })

    customers.sort(key=lambda item: item['updatedAt'] or datetime.min, reverse=True)
    return {
        'summary': {
            'customers': len(customers),
            'carts': total_carts,
            'lines': total_lines,
            'units': total_units,
            'value': f'{total_value:.2f}',
        },
        'customers': customers,
    }


class LoginInput(BaseModel):
    username: str
    password: str


class UserInput(BaseModel):
    username: str | None = None
    password: str | None = None
    full_name: str
    email: str | None = None
    nif: str | None = None
    company_name: str | None = None
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    delivery_address_line1: str | None = None
    delivery_address_line2: str | None = None
    delivery_postal_code: str | None = None
    delivery_city: str | None = None
    delivery_country: str | None = None
    delivery_same_as_billing: bool = True
    additional_emails: list[str] = Field(default_factory=list, max_length=10)
    carrier: str | None = None
    role: str = 'client'
    active: bool = True
    admin_notes: str | None = None
    catalogs: list[str] | None = None


class ActiveInput(BaseModel):
    active: bool


class CatalogAccessInput(BaseModel):
    catalogs: list[str] = Field(default_factory=list)


class CatalogInput(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    description: str | None = None
    icon: str = Field(default='mdi-bookshelf', min_length=4, max_length=80, pattern=r'^mdi-[a-z0-9-]+$')
    minimum_total: str = '0.00'
    sort_order: int = 0
    active: bool = True


class PasswordInput(BaseModel):
    password: str = Field(min_length=8)


class AccessInviteTokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class AccessInviteCreateInput(BaseModel):
    expires_in_hours: int = Field(default=1, ge=1, le=24 * 30)


class AccessInviteAcceptInput(AccessInviteTokenInput):
    password: str = Field(min_length=8, max_length=256)
    password_confirmation: str = Field(min_length=8, max_length=256)


class SendOrderPdfInput(BaseModel):
    hide_prices: bool = False


class PdfLayoutInput(BaseModel):
    showCustomer: bool = True
    showContact: bool = True
    showCarrier: bool = True
    showProductName: bool = True
    showSummary: bool = True
    showCategories: bool = True
    blankColumn: bool = True
    fontSize: str = 'normal'
    headerStyle: str = 'compact'
    showDocumentHeading: bool = False


class ProductInput(BaseModel):
    ref: str
    catalog_slug: str = 'villas'
    name: str
    product_type: str
    category_slug: str | None = None
    brand: str | None = None
    family: str | None = None
    ean: str | None = None
    price: str
    price_base: str | None = None
    eco_value: str = '0.000'
    pvp: str | None = None
    case_inner: int | None = Field(default=None, ge=1)
    case_outer: int | None = Field(default=None, ge=1)
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    season: str = 'ambos'
    quantity_step: int = Field(default=12, ge=1)
    quick_quantities: list[int] = Field(default_factory=list)
    sort_order: int = 0
    active: bool = True
    manual_active: bool = True
    gift_only: bool = False
    description: str | None = None


class CategoryInput(BaseModel):
    slug: str
    catalog_slug: str = 'villas'
    parent_slug: str | None = None
    label: str
    icon: str | None = Field(default=None, max_length=80, pattern=r'^mdi-[a-z0-9-]+$')
    sort_order: int = 0
    active: bool = True


class ProductImportCommitInput(BaseModel):
    rows: list[ProductInput] = Field(min_length=1, max_length=5000)
    categories: list[CategoryInput] = Field(default_factory=list, max_length=1000)
    update_existing: bool = True
    filename: str = Field(default='importacao', max_length=255)
    source_type: str = Field(default='spreadsheet', pattern=r'^(spreadsheet|pdf|csv)$')
    catalog: str = Field(default='villas', max_length=80)


class StatusInput(BaseModel):
    status: str
    note: str | None = None


class OrderNotesInput(BaseModel):
    notes: str | None = None


class OrderPdfNotesInput(BaseModel):
    notes: str | None = None
    include: bool = False


class WarningIgnoreInput(BaseModel):
    reason: str | None = None


class DraftCustomerInput(BaseModel):
    customer_id: int


class DraftLineInput(BaseModel):
    ref: str
    color: str | None = None
    size: str | None = None
    quantity: int = 1


class DraftNotesInput(BaseModel):
    notes: str | None = None
    pdf_notes: str | None = None
    include_pdf_notes: bool = False


class CampaignInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    show_text: bool = True
    active: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    sort_order: int = 0
    product_refs: list[str] = Field(default_factory=list, max_length=500)
    group_ids: list[int] = Field(default_factory=list, max_length=500)
    discount_type: str = Field(default='none', pattern='^(none|percentage|fixed_amount)$')
    discount_value: str = '0.000'
    promotional_prices: dict[str, str | None] = Field(default_factory=dict)


class CustomerGroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    active: bool = True
    user_ids: list[int] = Field(default_factory=list, max_length=5000)


class GiftPromotionTierInput(BaseModel):
    minimum_threshold: str
    maximum_threshold: str | None = None
    gift_product_ref: str = Field(min_length=1, max_length=80)
    gift_quantity: int = Field(default=1, ge=1, le=1000)


class GiftPromotionInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    catalog_slug: str = Field(min_length=1, max_length=80)
    eligibility_mode: str = Field(default='products', pattern='^(products|brands)$')
    eligible_brands: list[str] = Field(default_factory=list, max_length=500)
    condition_type: str = Field(pattern='^(quantity|value)$')
    threshold_quantity: int | None = Field(default=None, ge=1)
    threshold_value: str | None = None
    product_refs: list[str] = Field(default_factory=list, max_length=1000)
    gift_product_ref: str | None = Field(default=None, max_length=80)
    gift_quantity: int = Field(default=1, ge=1, le=1000)
    tiers: list[GiftPromotionTierInput] = Field(default_factory=list, max_length=50)
    max_redemptions_per_user: int = Field(default=1, ge=1, le=1000)
    active: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class UpdateMetadataInput(BaseModel):
    channel: str = Field(pattern='^(stable|beta|experimental|test)$')
    notify_admins_on_login: bool = True


class UpdateAnnouncementInput(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    selected_notes: list[str] = Field(min_length=1, max_length=200)


class CloudflareConnectionInput(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class CloudflareRecordInput(BaseModel):
    type: str = Field(pattern='^(A|AAAA|CNAME|MX|TXT)$')
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4096)
    ttl: int = Field(default=1, ge=1, le=86400)
    proxied: bool = False
    priority: int | None = Field(default=None, ge=0, le=65535)


class CloudflareDestinationInput(BaseModel):
    email: EmailStr


class CloudflareRuleInput(BaseModel):
    source: EmailStr
    destination: EmailStr
    enabled: bool = True


class SiteThemeInput(BaseModel):
    preset: str = Field(default='custom', min_length=1, max_length=40, pattern=r'^[a-z0-9-]+$')
    adminCanView: bool = False
    modeEnabled: bool = True
    mode: str = Field(default='light', pattern=r'^(light|dark|system)$')
    colorsEnabled: bool = True
    densityEnabled: bool = True
    density: str = Field(default='comfortable', pattern=r'^(compact|comfortable|spacious)$')
    cornersEnabled: bool = True
    corners: str = Field(default='soft', pattern=r'^(square|soft|rounded)$')
    shadowsEnabled: bool = True
    shadows: str = Field(default='subtle', pattern=r'^(none|subtle|normal)$')
    textSizeEnabled: bool = True
    textSize: str = Field(default='normal', pattern=r'^(small|normal|large)$')
    contentWidthEnabled: bool = True
    contentWidth: str = Field(default='standard', pattern=r'^(focused|standard|wide)$')
    motionEnabled: bool = True
    motion: str = Field(default='normal', pattern=r'^(none|subtle|normal)$')
    contrastEnabled: bool = True
    contrast: str = Field(default='standard', pattern=r'^(standard|high)$')
    tableStyleEnabled: bool = True
    tableStyle: str = Field(default='clean', pattern=r'^(clean|lines|striped)$')
    primary: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    secondary: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    accent: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    background: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    surface: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    darkPrimary: str = Field(default='#29466f', pattern=r'^#[0-9a-fA-F]{6}$')
    darkSecondary: str = Field(default='#d2ad62', pattern=r'^#[0-9a-fA-F]{6}$')
    darkAccent: str = Field(default='#7394c1', pattern=r'^#[0-9a-fA-F]{6}$')
    darkBackground: str = Field(default='#0f1726', pattern=r'^#[0-9a-fA-F]{6}$')
    darkSurface: str = Field(default='#172236', pattern=r'^#[0-9a-fA-F]{6}$')


class AppearancePreferenceInput(BaseModel):
    mode: str = Field(default='light', pattern=r'^(light|dark|system)$')


class AccountInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr | None = None
    additional_emails: list[EmailStr] = Field(default_factory=list, max_length=10)
    phone: str | None = Field(default=None, max_length=30)
    nif: str | None = Field(default=None, max_length=20)
    company_name: str | None = Field(default=None, max_length=150)
    carrier: str | None = Field(default=None, max_length=150)
    address_line1: str | None = Field(default=None, max_length=150)
    address_line2: str | None = Field(default=None, max_length=150)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    delivery_same_as_billing: bool = True
    delivery_address_line1: str | None = Field(default=None, max_length=150)
    delivery_address_line2: str | None = Field(default=None, max_length=150)
    delivery_postal_code: str | None = Field(default=None, max_length=20)
    delivery_city: str | None = Field(default=None, max_length=120)
    delivery_country: str | None = Field(default=None, max_length=120)


class AccountPasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)
    confirmation: str = Field(min_length=8, max_length=256)


class RepeatOrderInput(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)


def _api_user(request: Request) -> User:
    user = getattr(request.state, 'current_user', None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='login_required')
    return user


def _api_admin(user: User = Depends(_api_user)) -> User:
    if user.role not in {'admin', 'developer'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def _api_update_reader(user: User = Depends(_api_user)) -> User:
    if user.role not in {'admin', 'developer'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def _api_developer(user: User = Depends(_api_user)) -> User:
    if user.role != 'developer':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def _csrf(request: Request) -> None:
    auth_service.validate_csrf_submission(request, request.headers.get('X-CSRF-Token'))


def _cloudflare_error(exc: CloudflareServiceError) -> HTTPException:
    if exc.code == 'cloudflare_permission_denied':
        return HTTPException(status_code=403, detail=exc.code)
    if exc.code in {'cloudflare_not_configured', 'cloudflare_zone_not_found'}:
        return HTTPException(status_code=409, detail=exc.code)
    if exc.code in {'cloudflare_unavailable', 'cloudflare_request_failed'}:
        return HTTPException(status_code=502, detail=exc.code)
    return HTTPException(status_code=400, detail=exc.code)


def _masked_email(value: str) -> str:
    local, separator, domain = value.strip().partition('@')
    if not separator or not local or not domain:
        return ''
    visible = local[:2] if len(local) > 2 else local[:1]
    return f'{visible}{"*" * max(3, len(local) - len(visible))}@{domain}'


def _user_json(user: User, *, detailed: bool = False, db: Session | None = None) -> dict[str, Any]:
    catalogs = user_catalog_access(user)
    if db is not None and user.role in {'admin', 'developer'}:
        catalogs = [item.slug for item in catalog_service.list_catalogs(db)]
    result = {
        'id': user.id,
        'username': user.username,
        'fullName': user.full_name,
        'email': user.email or '',
        'nif': user.nif or '',
        'companyName': user.company_name or '',
        'phone': user.phone or '',
        'role': user.role,
        'active': bool(user.active),
        'lastLoginAt': user.last_login_at,
        'createdAt': user.created_at,
        'updatedAt': user.updated_at,
        'catalogs': catalogs,
        'appearanceMode': (user.metadata_json or {}).get('appearance_mode', 'light'),
    }
    if detailed:
        metadata = dict(user.metadata_json or {})
        result.update({
            'addressLine1': user.address_line1 or '',
            'addressLine2': user.address_line2 or '',
            'postalCode': user.postal_code or '',
            'city': user.city or '',
            'country': user.country or '',
            'deliveryAddressLine1': user.delivery_address_line1 or '',
            'deliveryAddressLine2': user.delivery_address_line2 or '',
            'deliveryPostalCode': user.delivery_postal_code or '',
            'deliveryCity': user.delivery_city or '',
            'deliveryCountry': user.delivery_country or '',
            'deliverySameAsBilling': bool(metadata.get('delivery_same_as_billing', not user.delivery_address_line1)),
            'additionalEmails': list(metadata.get('additional_emails') or []),
            'carrier': metadata.get('carrier') or '',
            'adminNotes': user.admin_notes or '',
        })
    return result


def _category_json(category: Category) -> dict[str, Any]:
    return {
        'slug': category.slug,
        'catalogSlug': category.catalog_slug,
        'parentSlug': category.parent_slug,
        'label': category.label,
        'icon': category.icon,
        'sortOrder': category.sort_order,
        'active': bool(category.active),
        'visibleOnSite': bool(category.visible_on_site),
    }


def _catalog_json(catalog: Catalog) -> dict[str, Any]:
    return {
        'slug': catalog.slug,
        'label': catalog.label,
        'description': catalog.description or '',
        'icon': catalog.icon or 'mdi-view-grid-outline',
        'minimumTotal': f'{Decimal(str(catalog.minimum_total or 0)):.2f}',
        'sortOrder': catalog.sort_order,
        'active': bool(catalog.active),
    }


def _catalog_slug(value: str) -> str:
    ascii_value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii').casefold()
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_value).strip('-')
    if not slug or len(slug) > 80 or slug in {'utilidades', 'admin', 'api'}:
        raise HTTPException(status_code=400, detail='invalid_catalog_slug')
    return slug


def _validate_catalog_access(db: Session, values: list[str]) -> list[str]:
    _ensure_system_catalogs(db)
    normalized = [str(value).strip().casefold() for value in values if str(value).strip()]
    existing = set(db.scalars(select(Catalog.slug).where(Catalog.slug.in_(normalized))).all()) if normalized else set()
    if set(normalized) != existing:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    return normalized


def _product_json(product: Product, promotion: PromotionInfo | None = None) -> dict[str, Any]:
    metadata = dict(product.metadata_json or {})
    quantity_step = normalize_qty_step(product.quantity_step, 1)
    configured_shortcuts = metadata.get('quick_quantities') or []
    quick_quantities = sorted({int(value) for value in configured_shortcuts if str(value).isdigit() and int(value) >= quantity_step and int(value) % quantity_step == 0})
    if not quick_quantities and product.catalog_slug == 'interpilhas':
        quick_quantities = sorted({int(value) for value in (product.case_inner, product.case_outer) if value and int(value) >= quantity_step and int(value) % quantity_step == 0})
    configured_zoom = metadata.get('image_zoom')
    try:
        image_zoom = max(0.75, min(1.7, float(configured_zoom)))
    except (TypeError, ValueError):
        image_zoom = 1.0
    effective_price = promotion.price if promotion else product.price
    effective_price_base = product.price_base
    if promotion and product.price_base is not None:
        effective_price_base = max(Decimal('0'), promotion.price - Decimal(str(product.eco_value or 0)))
    return {
        'ref': product.ref,
        'catalogSlug': product.catalog_slug,
        'catalogLabel': product.catalog.label if product.catalog else product.catalog_slug.title(),
        'name': product.name,
        'type': product.product_type,
        'categorySlug': product.category_slug,
        'categoryLabel': product.category.label if product.category else '',
        'categoryParentSlug': product.category.parent_slug if product.category else None,
        'categoryParentLabel': product.category.parent.label if product.category and product.category.parent else '',
        'categoryActive': bool(product.category.active and (product.category.parent is None or product.category.parent.active)) if product.category else True,
        'brand': product.brand or '',
        'family': product.family or '',
        'ean': product.ean or '',
        'price': f'{effective_price:.3f}' if product.catalog_slug == 'interpilhas' else f'{effective_price:.2f}',
        'priceBase': (f'{effective_price_base:.3f}' if product.catalog_slug == 'interpilhas' else f'{effective_price_base:.2f}') if effective_price_base is not None else None,
        'originalPrice': (f'{promotion.original_price:.3f}' if product.catalog_slug == 'interpilhas' else f'{promotion.original_price:.2f}') if promotion else None,
        'promotion': {'campaignId': promotion.campaign_id, 'title': promotion.campaign_title, 'label': promotion.label} if promotion else None,
        'ecoValue': f'{product.eco_value:.3f}' if product.catalog_slug == 'interpilhas' else f'{product.eco_value:.2f}',
        'pvp': f'{product.pvp:.2f}' if product.pvp is not None else None,
        'caseInner': product.case_inner,
        'caseOuter': product.case_outer,
        'colors': split_csv_values(product.colors_json or []),
        'sizes': split_csv_values(product.sizes_json or []),
        'imageUrl': f'/media/{product.image_path}' if product.image_path else None,
        'imageZoom': image_zoom,
        'sortOrder': product.sort_order,
        'active': bool(product.active),
        'manualActive': bool(product.manual_active),
        'giftOnly': bool(product.gift_only),
        'season': product.season,
        'quantityStep': quantity_step,
        'quickQuantities': quick_quantities[:4],
        'description': product.description or '',
    }


def _campaign_product_available(product: Product) -> bool:
    category = product.category
    return bool(
        product.active
        and product.manual_active
        and (product.catalog is None or product.catalog.active)
        and (category is None or (category.active and (category.parent is None or category.parent.active)))
    )


def _campaign_json(campaign: Campaign, *, user: User | None = None, admin: bool = False) -> dict[str, Any]:
    products = []
    for link in sorted(campaign.products, key=lambda item: (item.sort_order, item.id)):
        product = link.product
        if product is None:
            continue
        if not admin and (not _campaign_product_available(product) or (user is not None and not can_access_catalog(user, product.catalog_slug))):
            continue
        original_price = Decimal(str(product.price or 0)).quantize(Decimal('0.001'))
        campaign_price = price_for_campaign(product, campaign, link)
        promotion = PromotionInfo(campaign.id, campaign.title, original_price, campaign_price, campaign.discount_type if link.promotional_price is None else 'promotional_price', Decimal(str(campaign.discount_value or 0))) if campaign_price < original_price else None
        products.append(_product_json(product, promotion))
    now = utcnow()
    scheduled = bool((campaign.starts_at is None or campaign.starts_at <= now) and (campaign.ends_at is None or campaign.ends_at >= now))
    return {
        'id': campaign.id,
        'title': campaign.title,
        'description': campaign.description or '',
        'showText': bool(campaign.show_text),
        'active': bool(campaign.active),
        'currentlyActive': bool(campaign.active and scheduled),
        'startsAt': campaign.starts_at,
        'endsAt': campaign.ends_at,
        'sortOrder': campaign.sort_order,
        'discountType': campaign.discount_type,
        'discountValue': f'{Decimal(str(campaign.discount_value or 0)):.3f}',
        'imageUrl': f'/media/{campaign.image_path}' if campaign.image_path else None,
        'productRefs': [link.product_ref for link in sorted(campaign.products, key=lambda item: (item.sort_order, item.id))],
        'promotionalPrices': {link.product_ref: f'{link.promotional_price:.3f}' for link in campaign.products if link.promotional_price is not None},
        'groupIds': [link.group_id for link in campaign.audiences],
        'groups': [{'id': link.group.id, 'name': link.group.name, 'active': bool(link.group.active)} for link in campaign.audiences if link.group],
        'products': products,
        'createdAt': campaign.created_at,
        'updatedAt': campaign.updated_at,
    }


def _campaign_query():
    return select(Campaign).options(
        selectinload(Campaign.products).selectinload(CampaignProduct.product).selectinload(Product.catalog),
        selectinload(Campaign.products).selectinload(CampaignProduct.product).selectinload(Product.category).selectinload(Category.parent),
        selectinload(Campaign.audiences).selectinload(CampaignCustomerGroup.group),
    )


def _gift_promotion_query():
    return select(GiftPromotion).options(
        selectinload(GiftPromotion.products).selectinload(GiftPromotionProduct.product),
        selectinload(GiftPromotion.gift_product),
        selectinload(GiftPromotion.tiers).selectinload(GiftPromotionTier.gift_product),
        selectinload(GiftPromotion.redemptions).selectinload(GiftPromotionRedemption.user),
        selectinload(GiftPromotion.redemptions).selectinload(GiftPromotionRedemption.order),
    )


def _gift_promotion_json(promotion: GiftPromotion) -> dict[str, Any]:
    now = utcnow()
    scheduled = bool((promotion.starts_at is None or promotion.starts_at <= now) and (promotion.ends_at is None or promotion.ends_at >= now))
    redemptions = sorted(promotion.redemptions, key=lambda row: (row.created_at, row.id), reverse=True)
    recipient_count = len({row.user_id for row in redemptions})
    tiers = sorted(promotion.tiers, key=lambda row: (row.sort_order, row.minimum_threshold, row.id))
    return {
        'id': promotion.id,
        'title': promotion.title,
        'description': promotion.description or '',
        'catalogSlug': promotion.catalog_slug,
        'eligibilityMode': promotion.eligibility_mode,
        'eligibleBrands': list(promotion.eligible_brands_json or []),
        'conditionType': promotion.condition_type,
        'thresholdQuantity': promotion.threshold_quantity,
        'thresholdValue': f'{Decimal(str(promotion.threshold_value or 0)):.2f}',
        'productRefs': [link.product_ref for link in promotion.products],
        'products': [_product_json(link.product) for link in promotion.products if link.product],
        'giftProductRef': promotion.gift_product_ref,
        'giftProduct': _product_json(promotion.gift_product) if promotion.gift_product else None,
        'giftQuantity': promotion.gift_quantity,
        'tiers': [
            {
                'id': tier.id,
                'minimumThreshold': f'{Decimal(str(tier.minimum_threshold)):.3f}',
                'maximumThreshold': f'{Decimal(str(tier.maximum_threshold)):.3f}' if tier.maximum_threshold is not None else None,
                'giftProductRef': tier.gift_product_ref,
                'giftProduct': _product_json(tier.gift_product) if tier.gift_product else None,
                'giftQuantity': tier.gift_quantity,
                'sortOrder': tier.sort_order,
            }
            for tier in tiers
        ],
        'maxRedemptionsPerUser': promotion.max_redemptions_per_user,
        'active': bool(promotion.active),
        'currentlyActive': bool(promotion.active and scheduled),
        'startsAt': promotion.starts_at,
        'endsAt': promotion.ends_at,
        'redemptionCount': len(redemptions),
        'recipientCount': recipient_count,
        'redemptions': [
            {
                'id': row.id,
                'userId': row.user_id,
                'customerName': row.user.full_name if row.user else 'Cliente removido',
                'companyName': row.user.company_name if row.user else '',
                'orderId': row.order_id,
                'orderNumber': row.order.public_number if row.order else '',
                'createdAt': row.created_at,
            }
            for row in redemptions
        ],
        'createdAt': promotion.created_at,
        'updatedAt': promotion.updated_at,
    }


def _apply_gift_promotion_input(db: Session, promotion: GiftPromotion, payload: GiftPromotionInput) -> None:
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail='gift_promotion_invalid_period')
    catalog_slug = normalize_reference(payload.catalog_slug).casefold()
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    refs = list(dict.fromkeys(normalize_reference(ref) for ref in payload.product_refs if normalize_reference(ref)))
    products = list(db.scalars(select(Product).where(Product.ref.in_(refs), Product.catalog_slug == catalog_slug)).all())
    if payload.eligibility_mode == 'products' and (not refs or len(products) != len(refs)):
        raise HTTPException(status_code=400, detail='gift_promotion_product_not_found')
    available_brands = {
        str(brand).strip().casefold(): str(brand).strip()
        for brand in db.scalars(select(Product.brand).where(Product.catalog_slug == catalog_slug, Product.brand.is_not(None), Product.gift_only.is_(False))).all()
        if str(brand or '').strip()
    }
    requested_brands = list(dict.fromkeys(str(brand).strip().casefold() for brand in payload.eligible_brands if str(brand).strip()))
    if payload.eligibility_mode == 'brands' and (not requested_brands or any(brand not in available_brands for brand in requested_brands)):
        raise HTTPException(status_code=400, detail='gift_promotion_brand_not_found')
    tier_inputs = list(payload.tiers)
    if not tier_inputs:
        legacy_minimum = payload.threshold_value if payload.condition_type == 'value' else payload.threshold_quantity
        if legacy_minimum is None or not payload.gift_product_ref:
            raise HTTPException(status_code=400, detail='gift_promotion_threshold_required')
        tier_inputs = [GiftPromotionTierInput(
            minimum_threshold=str(legacy_minimum),
            gift_product_ref=payload.gift_product_ref,
            gift_quantity=payload.gift_quantity,
        )]
    normalized_tiers: list[tuple[Decimal, Decimal | None, Product, int]] = []
    for tier in tier_inputs:
        minimum = _decimal_3(tier.minimum_threshold)
        maximum = _decimal_3(tier.maximum_threshold)
        if minimum is None or minimum <= 0 or (maximum is not None and maximum <= minimum):
            raise HTTPException(status_code=400, detail='gift_promotion_tier_invalid')
        if payload.condition_type == 'quantity' and (
            minimum != minimum.to_integral_value()
            or (maximum is not None and maximum != maximum.to_integral_value())
        ):
            raise HTTPException(status_code=400, detail='gift_promotion_tier_invalid')
        gift = db.get(Product, normalize_reference(tier.gift_product_ref))
        if gift is None or gift.catalog_slug != catalog_slug:
            raise HTTPException(status_code=400, detail='gift_promotion_gift_not_found')
        if gift.ref in refs:
            raise HTTPException(status_code=400, detail='gift_promotion_gift_is_eligible')
        normalized_tiers.append((minimum, maximum, gift, tier.gift_quantity))
    normalized_tiers.sort(key=lambda row: row[0])
    for index, (minimum, _maximum, _gift, _quantity) in enumerate(normalized_tiers[1:], start=1):
        previous_maximum = normalized_tiers[index - 1][1]
        if previous_maximum is None or minimum < previous_maximum:
            raise HTTPException(status_code=400, detail='gift_promotion_tier_overlap')
    first_minimum, _first_maximum, first_gift, first_quantity = normalized_tiers[0]
    promotion.title = payload.title.strip()
    promotion.description = (payload.description or '').strip() or None
    promotion.catalog_slug = catalog_slug
    promotion.eligibility_mode = payload.eligibility_mode
    promotion.eligible_brands_json = [available_brands[brand] for brand in requested_brands] if payload.eligibility_mode == 'brands' else []
    promotion.condition_type = payload.condition_type
    promotion.threshold_quantity = int(first_minimum) if payload.condition_type == 'quantity' else None
    promotion.threshold_value = first_minimum if payload.condition_type == 'value' else None
    promotion.gift_product_ref = first_gift.ref
    promotion.gift_quantity = first_quantity
    promotion.max_redemptions_per_user = payload.max_redemptions_per_user
    promotion.active = payload.active
    promotion.starts_at = payload.starts_at.replace(tzinfo=None) if payload.starts_at and payload.starts_at.tzinfo else payload.starts_at
    promotion.ends_at = payload.ends_at.replace(tzinfo=None) if payload.ends_at and payload.ends_at.tzinfo else payload.ends_at
    promotion.products.clear()
    promotion.tiers.clear()
    db.flush()
    for ref in refs if payload.eligibility_mode == 'products' else []:
        promotion.products.append(GiftPromotionProduct(product_ref=ref))
    for sort_order, (minimum, maximum, gift, quantity) in enumerate(normalized_tiers):
        promotion.tiers.append(GiftPromotionTier(
            minimum_threshold=minimum,
            maximum_threshold=maximum,
            gift_product_ref=gift.ref,
            gift_quantity=quantity,
            sort_order=sort_order,
        ))
        gift.gift_only = True


def _apply_campaign_input(db: Session, campaign: Campaign, payload: CampaignInput) -> None:
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail='campaign_invalid_period')
    refs = list(dict.fromkeys(normalize_reference(ref) for ref in payload.product_refs if normalize_reference(ref)))
    products = list(db.scalars(select(Product).where(Product.ref.in_(refs))).all()) if refs else []
    products_by_ref = {product.ref: product for product in products}
    if len(products_by_ref) != len(refs):
        raise HTTPException(status_code=400, detail='campaign_product_not_found')
    group_ids = list(dict.fromkeys(int(group_id) for group_id in payload.group_ids))
    groups = list(db.scalars(select(CustomerGroup).where(CustomerGroup.id.in_(group_ids))).all()) if group_ids else []
    if len(groups) != len(group_ids):
        raise HTTPException(status_code=400, detail='customer_group_not_found')
    discount_value = _decimal_3(payload.discount_value, default=Decimal('0.000')) or Decimal('0.000')
    if discount_value < 0 or (payload.discount_type == 'percentage' and discount_value > 100):
        raise HTTPException(status_code=400, detail='campaign_discount_invalid')
    promotional_prices: dict[str, Decimal] = {}
    for raw_ref, raw_price in payload.promotional_prices.items():
        ref = normalize_reference(raw_ref)
        if ref not in products_by_ref or raw_price in (None, ''):
            continue
        price = _decimal_3(raw_price)
        if price is None or price < 0:
            raise HTTPException(status_code=400, detail='campaign_discount_invalid')
        promotional_prices[ref] = price
    campaign.title = payload.title.strip()
    campaign.description = (payload.description or '').strip() or None
    campaign.show_text = payload.show_text
    campaign.active = payload.active
    campaign.starts_at = payload.starts_at.replace(tzinfo=None) if payload.starts_at and payload.starts_at.tzinfo else payload.starts_at
    campaign.ends_at = payload.ends_at.replace(tzinfo=None) if payload.ends_at and payload.ends_at.tzinfo else payload.ends_at
    campaign.sort_order = payload.sort_order
    campaign.discount_type = payload.discount_type
    campaign.discount_value = discount_value
    campaign.products.clear()
    db.flush()
    for index, ref in enumerate(refs):
        campaign.products.append(CampaignProduct(product_ref=ref, sort_order=index, promotional_price=promotional_prices.get(ref)))
    campaign.audiences.clear()
    db.flush()
    for group_id in group_ids:
        campaign.audiences.append(CampaignCustomerGroup(group_id=group_id))


def _customer_group_json(group: CustomerGroup) -> dict[str, Any]:
    members = sorted((link.user for link in group.members if link.user), key=lambda item: (item.full_name.casefold(), item.id))
    return {
        'id': group.id,
        'name': group.name,
        'description': group.description or '',
        'active': bool(group.active),
        'userIds': [member.id for member in members],
        'members': [{'id': member.id, 'fullName': member.full_name, 'companyName': member.company_name or '', 'active': bool(member.active)} for member in members],
        'memberCount': len(members),
    }


def _customer_group_query():
    return select(CustomerGroup).options(selectinload(CustomerGroup.members).selectinload(CustomerGroupMember.user))


def _json(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


@router.get('/site/theme')
def site_theme(db: Session = Depends(get_db)):
    """Public, credential-free visual tokens used by the login and authenticated portal."""
    return _json({'theme': _site_theme(db)})


@router.get('/admin/site/theme')
def managed_site_theme(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    theme = _site_theme(db)
    if user.role != 'developer' and not theme['adminCanView']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='developer_only')
    return _json({'theme': theme, 'canEdit': user.role == 'developer'})


@router.put('/admin/site/theme')
def update_site_theme(
    payload: SiteThemeInput,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_api_developer),
):
    _csrf(request)
    normalized = {
        'preset': payload.preset.strip().casefold(),
        **{key: getattr(payload, key) for key in THEME_BOOLEAN_KEYS},
        **{key: getattr(payload, key).strip().casefold() for key in THEME_ENUMS},
        **{key: getattr(payload, key).lower() for key in THEME_COLOR_KEYS},
    }
    setting = db.get(SiteSetting, SITE_THEME_SETTING_KEY)
    if setting is None:
        setting = SiteSetting(key=SITE_THEME_SETTING_KEY, value=json.dumps(normalized, separators=(',', ':')))
        db.add(setting)
    else:
        setting.value = json.dumps(normalized, separators=(',', ':'))
    db.commit()
    return _json({'ok': True, 'theme': normalized})


@router.get('/session')
def session_state(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'current_user', None)
    return _json({
        'authenticated': user is not None,
        'user': _user_json(user, detailed=True, db=db) if user else None,
        'csrfToken': request.cookies.get('villas_v2_csrf', ''),
    })


@router.put('/user/appearance')
def update_user_appearance(
    payload: AppearancePreferenceInput,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_api_user),
):
    _csrf(request)
    target = db.get(User, user.id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
    metadata = dict(target.metadata_json or {})
    metadata['appearance_mode'] = payload.mode
    target.metadata_json = metadata
    db.commit()
    return _json({'ok': True, 'mode': payload.mode})


@router.get('/account')
def account_get(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    target = db.get(User, user.id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
    return _json({'user': _user_json(target, detailed=True, db=db)})


@router.put('/account')
def account_update(payload: AccountInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    _csrf(request)
    updated = user_service.update_user(
        db,
        user.id,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else '',
        nif=payload.nif or '',
        company_name=payload.company_name or '',
        phone=payload.phone or '',
        address_line1=payload.address_line1 or '',
        address_line2=payload.address_line2 or '',
        postal_code=payload.postal_code or '',
        city=payload.city or '',
        country=payload.country or '',
        delivery_address_line1=payload.delivery_address_line1 or '',
        delivery_address_line2=payload.delivery_address_line2 or '',
        delivery_postal_code=payload.delivery_postal_code or '',
        delivery_city=payload.delivery_city or '',
        delivery_country=payload.delivery_country or '',
        delivery_same_as_billing=payload.delivery_same_as_billing,
        additional_emails=[str(value) for value in payload.additional_emails],
        carrier=payload.carrier or '',
    )
    return _json({'ok': True, 'user': _user_json(updated, detailed=True, db=db)})


@router.put('/account/password')
def account_password(payload: AccountPasswordInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    _csrf(request)
    if payload.new_password != payload.confirmation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='password_mismatch')
    target = db.get(User, user.id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
    if not verify_password(target.password_hash, payload.current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='current_password_invalid')
    target.password_hash = hash_password(payload.new_password)
    current_session = getattr(request.state, 'current_session', None)
    current_session_id = getattr(current_session, 'session_token_hash', None)
    sessions = db.scalars(select(AppSession).where(AppSession.user_id == target.id, AppSession.revoked_at.is_(None))).all()
    now = utcnow()
    for session in sessions:
        if session.session_token_hash != current_session_id:
            session.revoked_at = now
    db.commit()
    return _json({'ok': True})


@router.get('/email/status')
def email_status(user: User = Depends(_api_admin)):
    """Small, credential-free SMTP health signal used by the application shell."""
    return _json({'ok': _smtp_health_snapshot()['ok']})


@router.post('/auth/login')
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = auth_service.authenticate(
        db,
        username=payload.username,
        password=payload.password,
        ip=request.state.client_ip,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_credentials')
    session_id, csrf_token = auth_service.create_session(
        db,
        user,
        ip=request.state.client_ip,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
        auth_context={'path': str(request.url.path), 'client_ip': request.state.client_ip},
    )
    response = _json({'ok': True, 'user': _user_json(user, detailed=True, db=db), 'csrfToken': csrf_token})
    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(settings.session_cookie_name, session_id, httponly=True, secure=settings.cookie_secure_flag, samesite=settings.cookie_samesite, max_age=max_age, path='/')
    response.set_cookie('villas_v2_csrf', csrf_token, httponly=False, secure=settings.cookie_secure_flag, samesite=settings.cookie_samesite, max_age=max_age, path='/')
    return response


@router.post('/auth/logout')
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    _csrf(request)
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        auth_service.revoke_session(db, session_id)
    response = _json({'ok': True})
    response.delete_cookie(settings.session_cookie_name, path='/')
    response.delete_cookie('villas_v2_csrf', path='/')
    return response


@router.get('/catalog')
def catalog_list(
    q: str | None = None,
    catalog: str = 'villas',
    category: str | None = None,
    subcategory: str | None = None,
    brand: str | None = None,
    family: str | None = None,
    season: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(_api_user),
):
    catalog_slug = normalize_reference(catalog).casefold() or 'villas'
    _ensure_system_catalogs(db)
    selected_catalog = db.get(Catalog, catalog_slug)
    if selected_catalog is None or not selected_catalog.active:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    if not can_access_catalog(user, catalog_slug):
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    result = catalog_service.list_products(
        db,
        q=q,
        catalog=catalog_slug,
        category=category,
        subcategory=subcategory,
        brand=brand,
        family=family,
        season=season,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    promotions = active_promotions(db, user.id, result.items)
    return _json({
        'items': [_product_json(item, promotions.get(item.ref)) for item in result.items],
        'total': result.total,
        'page': result.page,
        'pages': result.pages,
        'perPage': result.per_page,
        'catalog': _catalog_json(selected_catalog),
        'catalogs': [_catalog_json(item) for item in catalog_service.list_catalogs(db) if can_access_catalog(user, item.slug)],
        'categories': [_category_json(item) for item in catalog_service.list_categories(db, catalog=catalog_slug)],
        'filters': catalog_service.filter_options(db, catalog=catalog_slug),
    })


@router.get('/catalog/navigation')
def catalog_navigation(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    """Small permission-aware category tree used by the responsive sidebar."""
    _ensure_system_catalogs(db)
    result: list[dict[str, Any]] = []
    for catalog in catalog_service.list_catalogs(db):
        if not can_access_catalog(user, catalog.slug):
            continue
        categories = [
            category
            for category in catalog_service.list_categories(db, catalog=catalog.slug)
            if category.visible_on_site
        ]
        children_by_parent: dict[str, list[Category]] = {}
        for category in categories:
            if category.parent_slug:
                children_by_parent.setdefault(category.parent_slug, []).append(category)
        top_level = []
        for category in categories:
            if category.parent_slug:
                continue
            entry = _category_json(category)
            entry['children'] = [_category_json(child) for child in children_by_parent.get(category.slug, [])]
            top_level.append(entry)
        catalog_entry = _catalog_json(catalog)
        if catalog.slug == 'interpilhas':
            catalog_entry['label'] = 'Utilidades'
        catalog_entry['categories'] = top_level
        result.append(catalog_entry)
    return _json({'catalogs': result})


@router.get('/campaigns/active')
def active_campaigns(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    now = utcnow()
    rows = list(db.scalars(
        _campaign_query()
        .where(
            Campaign.active.is_(True),
            or_(Campaign.starts_at.is_(None), Campaign.starts_at <= now),
            or_(Campaign.ends_at.is_(None), Campaign.ends_at >= now),
        )
        .order_by(Campaign.sort_order, Campaign.id)
    ).unique().all())
    if user.role not in {'admin', 'developer'}:
        user_group_ids = set(db.scalars(select(CustomerGroupMember.group_id).where(CustomerGroupMember.user_id == user.id)).all())
        rows = [row for row in rows if not row.audiences or any(link.group_id in user_group_ids and link.group and link.group.active for link in row.audiences)]
    campaigns = [_campaign_json(row, user=user) for row in rows]
    return _json({'campaigns': [campaign for campaign in campaigns if campaign['products']]})


@router.get('/catalog/{catalog}/{ref}')
def catalog_detail_scoped(catalog: str, ref: str, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    if not can_access_catalog(user, catalog):
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    product = catalog_service.get_product(db, ref, catalog=catalog)
    if product is None or (product.gift_only and user.role not in {'admin', 'developer'}):
        raise HTTPException(status_code=404, detail='product_not_found')
    promotion = active_promotions(db, user.id, [product]).get(product.ref)
    return _json({'product': _product_json(product, promotion)})


@router.get('/catalog/{ref}')
def catalog_detail(ref: str, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    if not can_access_catalog(user, 'villas'):
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    product = catalog_service.get_product(db, ref, catalog='villas')
    if product is None or (product.gift_only and user.role not in {'admin', 'developer'}):
        raise HTTPException(status_code=404, detail='product_not_found')
    promotion = active_promotions(db, user.id, [product]).get(product.ref)
    return _json({'product': _product_json(product, promotion)})


@router.get('/cart')
def cart_get(catalog: str = Query(default='villas'), db: Session = Depends(get_db), user: User = Depends(_api_user)):
    catalog_slug = normalize_reference(catalog).casefold() or 'villas'
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    if not can_access_catalog(user, catalog_slug):
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    return _json({'cart': cart_service.get_cart(db, user.id, catalog_slug)})


@router.get('/orders')
def orders_get(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    orders = order_service.list_admin_orders(db, limit=1000) if user.role in {'admin', 'developer'} else order_service.list_client_orders(db, user_id=user.id)
    return _json({'orders': orders})


@router.get('/orders/{identifier}')
def order_get(identifier: str, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    admin_access = user.role in {'admin', 'developer'}
    order = order_service.get_order(db, identifier, admin=admin_access, user_id=None if admin_access else user.id)
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    history = order_service.status_history(db, order['id'])
    if user.role not in {'admin', 'developer'}:
        history = [{**item, 'note': ''} for item in history]
    return _json({'order': order, 'history': history, 'emailLogs': order_service.email_logs(db, order['id']) if user.role in {'admin', 'developer'} else []})


@router.post('/orders/{identifier}/repeat')
def order_repeat(identifier: str, payload: RepeatOrderInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    _csrf(request)
    order = order_service.get_order(db, identifier, admin=False, user_id=user.id)
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    catalog_slug = normalize_reference(order.get('catalogSlug')).casefold() or 'villas'
    if not can_access_catalog(user, catalog_slug):
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    current = cart_service.get_cart(db, user.id, catalog_slug)
    merged = [
        {'ref': item['ref'], 'color': item.get('color', ''), 'size': item.get('size', ''), 'quantity': item['quantity']}
        for item in current['items'] if not item.get('is_gift')
    ]
    skipped: list[dict[str, str]] = []
    added = 0
    for line in order.get('items', []):
        if (line.get('snapshot') or {}).get('is_gift'):
            continue
        product = db.get(Product, normalize_reference(line.get('ref')))
        if product is None or product.catalog_slug != catalog_slug or product.gift_only or not cart_service._product_is_available(product):
            skipped.append({'ref': str(line.get('ref') or ''), 'reason': 'indisponível'})
            continue
        colors = split_csv_values(product.colors_json or [])
        sizes = split_csv_values(product.sizes_json or [])
        color = str(line.get('color') or '')
        size = str(line.get('size') or '')
        if (colors and color not in colors) or (sizes and size not in sizes):
            skipped.append({'ref': product.ref, 'reason': 'variante indisponível'})
            continue
        step = normalize_qty_step(product.quantity_step, default=1)
        previous_quantity = max(1, int(line.get('quantity') or step))
        quantity = ((previous_quantity + step - 1) // step) * step
        merged.append({'ref': product.ref, 'color': color, 'size': size, 'quantity': quantity})
        added += 1
    if added == 0:
        raise HTTPException(status_code=409, detail='repeat_order_no_available_products')
    revision = int(current['revision'])
    db.rollback()
    cart = cart_service.replace_cart(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        items=merged,
        expected_revision=revision,
        catalog_slug=catalog_slug,
    )
    return _json({'ok': True, 'catalog': catalog_slug, 'added': added, 'skipped': skipped, 'cart': cart})


@router.get('/orders/{identifier}/pdf')
def order_pdf(
    identifier: str,
    hide_prices: bool = Query(default=False),
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(_api_user),
):
    order = order_service.get_order(
        db,
        identifier,
        admin=user.role in {'admin', 'developer'},
        user_id=None if user.role in {'admin', 'developer'} else user.id,
    )
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    filename = f"{order['publicNumber']}{'_sem_precos' if hide_prices else ''}.pdf"
    return Response(
        content=build_order_pdf(order, hide_prices=hide_prices, layout=get_pdf_layout(db, kind='no_prices' if hide_prices else 'priced', user_id=order['userId'])),
        media_type='application/pdf',
        headers={'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'},
    )


@router.get('/admin/pdf-layout')
def pdf_layout_get(kind: str = Query(default='no_prices', pattern='^(no_prices|priced)$'), user_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    if user_id is not None and user_service.get_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    return _json({'kind': kind, 'userId': user_id, 'customized': bool(user_id and has_user_pdf_layout(db, user_id, kind=kind)), 'layout': get_pdf_layout(db, kind=kind, user_id=user_id)})


@router.put('/admin/pdf-layout')
def pdf_layout_put(payload: PdfLayoutInput, request: Request, kind: str = Query(default='no_prices', pattern='^(no_prices|priced)$'), user_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user_id is not None:
        if user_service.get_user(db, user_id) is None:
            raise HTTPException(status_code=404, detail='user_not_found')
        layout = save_user_pdf_layout(db, user_id, payload.model_dump(), kind=kind)
    else:
        layout = save_pdf_layout(db, payload.model_dump(), kind=kind)
    return _json({'ok': True, 'kind': kind, 'userId': user_id, 'customized': user_id is not None, 'layout': layout})


@router.delete('/admin/pdf-layout')
def pdf_layout_reset(request: Request, kind: str = Query(default='no_prices', pattern='^(no_prices|priced)$'), user_id: int = Query(), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user_service.get_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    return _json({'ok': True, 'kind': kind, 'userId': user_id, 'customized': False, 'layout': reset_user_pdf_layout(db, user_id, kind=kind)})


@router.post('/admin/orders/{identifier}/pdf-preview')
def pdf_layout_preview(identifier: str, payload: PdfLayoutInput, request: Request, kind: str = Query(default='no_prices', pattern='^(no_prices|priced)$'), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = order_service.get_order(db, identifier, admin=True)
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    return Response(
        content=build_order_pdf(order, hide_prices=kind == 'no_prices', layout=normalize_pdf_layout(payload.model_dump(), kind=kind)),
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{order["publicNumber"]}_previsualizacao.pdf"'},
    )


@router.patch('/admin/orders/{identifier}/status')
def order_status(identifier: str, payload: StatusInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = order_service.change_status(db, identifier=identifier, new_status=payload.status, changed_by_user_id=user.id, request_id=getattr(request.state, 'request_id', None), note=payload.note)
    if order.get('statusChanged'):
        EmailService().send_order_event(db, order=order, event=f"order_{order['orderStatus']}", request_id=getattr(request.state, 'request_id', None), related_user_id=order['userId'])
    return _json({'ok': True, 'order': order})


@router.patch('/admin/orders/{identifier}/notes')
def order_internal_notes(identifier: str, payload: OrderNotesInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = order_service.update_internal_notes(
        db,
        identifier=identifier,
        notes=payload.notes,
        changed_by_user_id=user.id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _json({'ok': True, 'order': order})


@router.patch('/admin/orders/{identifier}/pdf-notes')
def order_pdf_notes(identifier: str, payload: OrderPdfNotesInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = order_service.update_pdf_notes(
        db,
        identifier=identifier,
        notes=payload.notes,
        include=payload.include,
        changed_by_user_id=user.id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _json({'ok': True, 'order': order})


@router.delete('/admin/orders/{identifier}')
def order_delete(identifier: str, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order_data = order_service.get_order(db, identifier, admin=True)
    if order_data is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    order = db.get(Order, order_data['id'])
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    # Preserve email audit records while removing the order and its dependent lines/history.
    db.query(EmailDeliveryLog).filter(EmailDeliveryLog.related_order_id == order.id).update({EmailDeliveryLog.related_order_id: None})
    db.query(OrderRequestId).filter(OrderRequestId.order_id == order.id).delete()
    db.delete(order)
    db.commit()
    return _json({'ok': True})


@router.get('/admin/dashboard')
def admin_dashboard(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json({
        'metrics': asdict(stats_service.dashboard_metrics(db)),
        'monthlySeries': [asdict(row) for row in stats_service.monthly_series(db, months=12)],
        'recentOrders': order_service.list_admin_orders(db, limit=8),
        'recentCustomers': [_user_json(item) for item in user_service.list_users(db, role='client', limit=8)],
        'pendingCartActivity': _pending_cart_overview(db),
    })


@router.get('/admin/system-health')
def system_health(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    database_started = perf_counter()
    try:
        db.execute(select(1)).scalar_one()
        database = {'ok': True, 'durationMs': round((perf_counter() - database_started) * 1000, 1)}
    except Exception as exc:
        database = {'ok': False, 'durationMs': round((perf_counter() - database_started) * 1000, 1), 'reason': type(exc).__name__}

    smtp = _smtp_health_snapshot()
    storage_paths = [settings.media_root, settings.media_root / 'products', settings.log_dir]
    storage = {
        'ok': all(path.exists() and os.access(path, os.W_OK) for path in storage_paths),
        'pathsChecked': len(storage_paths),
    }
    runtime = diagnostics.snapshot()
    monitor_setting = db.get(SiteSetting, 'monitor.last_state')
    try:
        monitoring = json.loads(monitor_setting.value) if monitor_setting else None
    except (TypeError, ValueError):
        monitoring = None
    overall_ok = bool(database['ok'] and smtp['ok'] and storage['ok'])
    return _json({
        'status': 'ok' if overall_ok else 'degraded',
        'database': database,
        'email': {
            'ok': bool(smtp['ok']),
            'durationMs': smtp['durationMs'],
            'configured': bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from),
        },
        'storage': storage,
        'runtime': runtime,
        'monitoring': monitoring,
        'versions': {
            'fastapi': _package_version('fastapi'),
            'sqlalchemy': _package_version('sqlalchemy'),
            'pydantic': _package_version('pydantic'),
        },
    })


@router.get('/admin/cloudflare')
def developer_cloudflare_dashboard(user: User = Depends(_api_developer)):
    try:
        portal_email = settings.smtp_from or settings.smtp_user
        return _json({
            **cloudflare_service.dashboard(),
            'portalEmailConfigured': bool(portal_email),
            'portalEmailMasked': _masked_email(portal_email),
        })
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.put('/admin/cloudflare/connection')
def developer_cloudflare_connection(payload: CloudflareConnectionInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'zone': cloudflare_service.save_token(payload.token)})
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.post('/admin/cloudflare/dns-records')
def developer_cloudflare_record_create(payload: CloudflareRecordInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'record': cloudflare_service.save_record(payload.model_dump())}, 201)
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.put('/admin/cloudflare/dns-records/{record_id}')
def developer_cloudflare_record_update(record_id: str, payload: CloudflareRecordInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'record': cloudflare_service.save_record(payload.model_dump(), record_id=record_id)})
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.delete('/admin/cloudflare/dns-records/{record_id}')
def developer_cloudflare_record_delete(record_id: str, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        cloudflare_service.delete_record(record_id)
        return _json({'ok': True})
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.post('/admin/cloudflare/email/destinations')
def developer_cloudflare_destination_create(payload: CloudflareDestinationInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'destination': cloudflare_service.create_destination(str(payload.email))}, 201)
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.post('/admin/cloudflare/email/destinations/portal')
def developer_cloudflare_portal_destination_create(request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    portal_email = (settings.smtp_from or settings.smtp_user).strip()
    if not portal_email:
        raise HTTPException(status_code=409, detail='portal_email_not_configured')
    try:
        destination = cloudflare_service.create_destination(portal_email)
        return _json({'ok': True, 'destination': {**destination, 'email': _masked_email(portal_email)}}, 201)
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.post('/admin/cloudflare/email/rules')
def developer_cloudflare_rule_create(payload: CloudflareRuleInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'rule': cloudflare_service.save_rule(source=str(payload.source), destination=str(payload.destination), enabled=payload.enabled)}, 201)
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.put('/admin/cloudflare/email/rules/{rule_id}')
def developer_cloudflare_rule_update(rule_id: str, payload: CloudflareRuleInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        return _json({'ok': True, 'rule': cloudflare_service.save_rule(source=str(payload.source), destination=str(payload.destination), rule_id=rule_id, enabled=payload.enabled)})
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.delete('/admin/cloudflare/email/rules/{rule_id}')
def developer_cloudflare_rule_delete(rule_id: str, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        cloudflare_service.delete_rule(rule_id)
        return _json({'ok': True})
    except CloudflareServiceError as exc:
        raise _cloudflare_error(exc) from exc


@router.get('/admin/system-update')
def system_update_status(user: User = Depends(_api_update_reader)):
    return _json({**update_status(), 'canEditRelease': user.role == 'developer', 'canInstall': user.role in {'admin', 'developer'}})


@router.put('/admin/system-update/metadata')
def system_update_metadata(payload: UpdateMetadataInput, request: Request, user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        pending = update_pending_metadata(channel=payload.channel, notify_admins_on_login=payload.notify_admins_on_login)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='pending_update_not_found') from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='invalid_update_channel') from exc
    return _json({'ok': True, 'pending': pending})


@router.post('/admin/system-update/apply', status_code=status.HTTP_202_ACCEPTED)
def system_update_apply(request: Request, user: User = Depends(_api_admin)):
    _csrf(request)
    result = start_update()
    if not result['started']:
        raise HTTPException(status_code=409, detail='update_not_ready')
    return _json(result, status.HTTP_202_ACCEPTED)


@router.get('/admin/system-update/announcement-center')
def update_announcement_center(db: Session = Depends(get_db), user: User = Depends(_api_developer)):
    return _json(update_announcements.developer_center(db))


@router.post('/admin/system-update/announcements', status_code=status.HTTP_201_CREATED)
def update_announcement_create(payload: UpdateAnnouncementInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        row = update_announcements.create_announcement(db, version=payload.version, selected_notes=payload.selected_notes, created_by_user_id=user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _json({'ok': True, 'announcementId': row.id}, status.HTTP_201_CREATED)


@router.patch('/admin/system-update/announcements/{announcement_id}')
def update_announcement_toggle(announcement_id: int, payload: ActiveInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        row = update_announcements.set_announcement_active(db, announcement_id, payload.active)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _json({'ok': True, 'active': row.active})


@router.delete('/admin/system-update/announcements/{announcement_id}')
def update_announcement_delete(announcement_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_developer)):
    _csrf(request)
    try:
        update_announcements.delete_announcement(db, announcement_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _json({'ok': True})


@router.get('/system-update/announcement')
def update_announcement_for_admin(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json({'announcement': update_announcements.next_for_admin(db, user.id) if user.role == 'admin' else None})


@router.post('/system-update/announcements/{announcement_id}/viewed')
def update_announcement_viewed(announcement_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user.role != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    try:
        update_announcements.mark_viewed(db, announcement_id, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _json({'ok': True})


@router.post('/system-update/announcements/{announcement_id}/acknowledged')
def update_announcement_acknowledged(announcement_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user.role != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    try:
        update_announcements.mark_viewed(db, announcement_id, user.id, action='acknowledged')
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _json({'ok': True})


@router.post('/system-update/announcements/{announcement_id}/ignored')
def update_announcement_ignored(announcement_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user.role != 'admin':
        raise HTTPException(status_code=403, detail='forbidden')
    try:
        update_announcements.mark_viewed(db, announcement_id, user.id, action='ignored')
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _json({'ok': True})


@router.get('/admin/pending-carts')
def pending_carts_overview(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json(_pending_cart_overview(db))


@router.get('/admin/users')
def users_list(q: str | None = None, role: str | None = None, active: bool | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    users = user_service.list_users(db, limit=1000, q=q, role=role, active=active)
    all_users = user_service.list_users(db, limit=2000)
    clients = [item for item in all_users if item.role == 'client']
    return _json({'users': [_user_json(item, db=db) for item in users], 'catalogs': [_catalog_json(item) for item in catalog_service.list_catalogs(db, include_inactive=True)], 'counts': {'all': len(all_users), 'client': len(clients), 'admin': sum(item.role == 'admin' for item in all_users), 'active': sum(item.active for item in all_users), 'inactive': sum(not item.active for item in all_users)}, 'allClientsActive': bool(clients) and all(item.active for item in clients)})


@router.post('/admin/users')
def user_create(payload: UserInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail='username_and_password_required')
    created = user_service.create_user(db, username=payload.username, password=payload.password, full_name=payload.full_name, role=payload.role, email=payload.email, nif=payload.nif, company_name=payload.company_name, phone=payload.phone, address_line1=payload.address_line1, address_line2=payload.address_line2, postal_code=payload.postal_code, city=payload.city, country=payload.country, delivery_address_line1=payload.delivery_address_line1, delivery_address_line2=payload.delivery_address_line2, delivery_postal_code=payload.delivery_postal_code, delivery_city=payload.delivery_city, delivery_country=payload.delivery_country, delivery_same_as_billing=payload.delivery_same_as_billing, additional_emails=payload.additional_emails, carrier=payload.carrier, active=payload.active)
    set_user_catalog_access(created, _validate_catalog_access(db, payload.catalogs) if payload.catalogs is not None else ['villas'])
    db.commit()
    db.refresh(created)
    email_result = EmailService().send_user_created(db, user=created, password=payload.password, request_id=getattr(request.state, 'request_id', None))
    return _json({'ok': True, 'user': _user_json(created, detailed=True), 'emailStatus': email_result.status}, 201)


@router.get('/admin/users/{user_id}')
def user_detail(user_id: int, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    target = user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    catalogs = catalog_service.list_catalogs(db, include_inactive=True)
    orders = order_service.list_client_orders(db, user_id=target.id)
    return _json({'user': _user_json(target, detailed=True, db=db), 'accessInvite': _access_invite_status(db, target.id), 'activity': _user_commercial_activity(db, target.id, catalogs=catalogs, orders=orders), 'catalogs': [_catalog_json(item) for item in catalogs], 'orders': orders, 'warnings': [asdict(item) for item in warning_service.list_warnings(db) if item.entity_id == target.id]})


@router.get('/admin/users/{user_id}/commercial-activity')
def user_commercial_activity(user_id: int, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    if user_service.get_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    return _json({'activity': _user_commercial_activity(db, user_id)})


@router.get('/admin/users/{user_id}/access-invite-status')
def user_access_invite_status(user_id: int, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    if user_service.get_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    return _json({'accessInvite': _access_invite_status(db, user_id)})


@router.put('/admin/users/{user_id}')
def user_update(user_id: int, payload: UserInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    updated = user_service.update_user(db, user_id, full_name=payload.full_name, email=payload.email, nif=payload.nif, company_name=payload.company_name, phone=payload.phone, address_line1=payload.address_line1, address_line2=payload.address_line2, postal_code=payload.postal_code, city=payload.city, country=payload.country, delivery_address_line1=payload.delivery_address_line1, delivery_address_line2=payload.delivery_address_line2, delivery_postal_code=payload.delivery_postal_code, delivery_city=payload.delivery_city, delivery_country=payload.delivery_country, delivery_same_as_billing=payload.delivery_same_as_billing, additional_emails=payload.additional_emails, carrier=payload.carrier, role=payload.role, active=payload.active, admin_notes=payload.admin_notes)
    if payload.catalogs is not None:
        set_user_catalog_access(updated, _validate_catalog_access(db, payload.catalogs))
        db.commit()
        db.refresh(updated)
    return _json({'ok': True, 'user': _user_json(updated, detailed=True)})


@router.patch('/admin/users/{user_id}/active')
def user_active(user_id: int, payload: ActiveInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    updated = user_service.set_active(db, user_id, payload.active)
    return _json({'ok': True, 'user': _user_json(updated)})


@router.patch('/admin/users/{user_id}/catalogs')
def user_catalogs(user_id: int, payload: CatalogAccessInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    target = user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    set_user_catalog_access(target, _validate_catalog_access(db, payload.catalogs))
    db.commit()
    db.refresh(target)
    return _json({'ok': True, 'user': _user_json(target, detailed=True)})


@router.patch('/admin/clients/active')
def clients_active(payload: ActiveInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'ok': True, 'updated': user_service.set_all_clients_active(db, payload.active)})


@router.put('/admin/users/{user_id}/password')
def user_password(user_id: int, payload: PasswordInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    user_service.reset_password(db, user_id, payload.password)
    auth_service.revoke_user_sessions(db, user_id)
    return _json({'ok': True})


@router.post('/admin/users/{user_id}/welcome-email')
def user_resend_welcome_email(user_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    target = user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    temporary_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    target = user_service.reset_password(db, user_id, temporary_password)
    auth_service.revoke_user_sessions(db, user_id)
    result = EmailService().send_user_created(db, user=target, password=temporary_password, request_id=getattr(request.state, 'request_id', None))
    if result.status != 'sent':
        raise HTTPException(status_code=502, detail=result.error_message or 'email_delivery_failed')
    return _json({'ok': True, 'emailStatus': result.status})


@router.post('/admin/users/{user_id}/share-access')
def user_share_access(user_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    target = user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    temporary_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    target = user_service.reset_password(db, user_id, temporary_password)
    auth_service.revoke_user_sessions(db, user_id)
    return _json({'ok': True, 'access': {
        'fullName': target.full_name,
        'username': target.username,
        'password': temporary_password,
        'loginUrl': settings.public_url.rstrip('/') + '/',
    }})


@router.post('/admin/users/{user_id}/access-invite')
def user_access_invite(user_id: int, request: Request, payload: AccessInviteCreateInput | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    expires_in_hours = payload.expires_in_hours if payload else 1
    target, invite, token = create_access_invite(
        db,
        user_id=user_id,
        created_by_user_id=user.id,
        expires_in_hours=expires_in_hours,
    )
    return _json({'ok': True, 'invite': {
        'fullName': target.full_name,
        'username': target.username,
        'url': f"{settings.public_url.rstrip('/')}/convite?token={token}",
        'status': 'valid',
        'createdAt': invite.created_at,
        'expiresAt': invite.expires_at,
        'expiresInSeconds': expires_in_hours * 3600,
    }})


@router.post('/access-invite/inspect')
def access_invite_inspect(payload: AccessInviteTokenInput, db: Session = Depends(get_db)):
    invite, target = get_access_invite(db, payload.token)
    return _json({'invite': {
        'fullName': target.full_name,
        'username': target.username,
        'expiresAt': invite.expires_at,
    }})


@router.post('/access-invite/accept')
def access_invite_accept(payload: AccessInviteAcceptInput, db: Session = Depends(get_db)):
    if payload.password != payload.password_confirmation:
        raise HTTPException(status_code=400, detail='password_mismatch')
    target = accept_access_invite(db, token=payload.token, password=payload.password)
    return _json({'ok': True, 'username': target.username})


@router.post('/admin/users/{user_id}/orders/{identifier}/email-pdf')
def order_send_pdf_to_user(user_id: int, identifier: str, payload: SendOrderPdfInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    target = user_service.get_user(db, user_id)
    order = order_service.get_order(db, identifier, admin=True)
    if target is None or order is None or order.get('userId') != user_id:
        raise HTTPException(status_code=404, detail='order_not_found')
    result = EmailService().send_order_pdf(
        db, order=order, recipients=EmailService.user_recipients(target), hide_prices=payload.hide_prices,
        request_id=getattr(request.state, 'request_id', None), related_user_id=target.id,
    )
    if result.status != 'sent':
        raise HTTPException(status_code=502, detail=result.error_message or 'email_delivery_failed')
    return _json({'ok': True, 'emailStatus': result.status})


@router.delete('/admin/users/{user_id}')
def user_delete(user_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if user.id == user_id:
        raise HTTPException(status_code=409, detail='cannot_delete_self')
    if not user_service.delete_user(db, user_id):
        raise HTTPException(status_code=409, detail='user_has_history')
    return _json({'ok': True})


@router.get('/admin/catalog')
def admin_catalog(q: str | None = None, catalog: str | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _ensure_system_catalogs(db)
    page = catalog_service.list_products(db, q=q, catalog=catalog, include_inactive=True, page=1, per_page=5000)
    return _json({
        'products': [_product_json(item) for item in page.items],
        'catalogs': [_catalog_json(item) for item in catalog_service.list_catalogs(db, include_inactive=True)],
        'categories': [_category_json(item) for item in catalog_service.list_categories(db, catalog=catalog, include_inactive=True)],
        'counts': catalog_service.catalog_counts(db, catalog=catalog),
    })


@router.get('/admin/campaigns')
def admin_campaigns(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    rows = list(db.scalars(_campaign_query().order_by(Campaign.sort_order, desc(Campaign.id))).unique().all())
    return _json({'campaigns': [_campaign_json(row, admin=True) for row in rows]})


def _apply_customer_group_input(db: Session, group: CustomerGroup, payload: CustomerGroupInput) -> None:
    name = payload.name.strip()
    duplicate = db.scalar(select(CustomerGroup).where(func.lower(CustomerGroup.name) == name.casefold(), CustomerGroup.id != (group.id or 0)))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail='customer_group_exists')
    user_ids = list(dict.fromkeys(int(user_id) for user_id in payload.user_ids))
    clients = list(db.scalars(select(User).where(User.id.in_(user_ids), User.role == 'client')).all()) if user_ids else []
    if len(clients) != len(user_ids):
        raise HTTPException(status_code=400, detail='customer_group_user_invalid')
    group.name = name
    group.description = (payload.description or '').strip() or None
    group.active = payload.active
    group.members.clear()
    db.flush()
    for user_id in user_ids:
        group.members.append(CustomerGroupMember(user_id=user_id))


@router.get('/admin/customer-groups')
def admin_customer_groups(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    rows = list(db.scalars(_customer_group_query().order_by(CustomerGroup.name)).unique().all())
    return _json({'groups': [_customer_group_json(row) for row in rows]})


@router.post('/admin/customer-groups')
def admin_customer_group_create(payload: CustomerGroupInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    group = CustomerGroup(name=payload.name.strip())
    db.add(group)
    _apply_customer_group_input(db, group, payload)
    db.commit()
    group = db.scalar(_customer_group_query().where(CustomerGroup.id == group.id))
    return _json({'ok': True, 'group': _customer_group_json(group)}, 201)


@router.put('/admin/customer-groups/{group_id}')
def admin_customer_group_update(group_id: int, payload: CustomerGroupInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    group = db.scalar(_customer_group_query().where(CustomerGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=404, detail='customer_group_not_found')
    _apply_customer_group_input(db, group, payload)
    db.commit()
    group = db.scalar(_customer_group_query().where(CustomerGroup.id == group_id))
    return _json({'ok': True, 'group': _customer_group_json(group)})


@router.delete('/admin/customer-groups/{group_id}')
def admin_customer_group_delete(group_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    group = db.get(CustomerGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail='customer_group_not_found')
    db.delete(group)
    db.commit()
    return _json({'ok': True})


@router.post('/admin/campaigns')
def admin_campaign_create(payload: CampaignInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    campaign = Campaign(title=payload.title.strip())
    db.add(campaign)
    _apply_campaign_input(db, campaign, payload)
    db.commit()
    campaign = db.scalar(_campaign_query().where(Campaign.id == campaign.id))
    return _json({'ok': True, 'campaign': _campaign_json(campaign, admin=True)}, 201)


@router.put('/admin/campaigns/{campaign_id}')
def admin_campaign_update(campaign_id: int, payload: CampaignInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    campaign = db.scalar(_campaign_query().where(Campaign.id == campaign_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail='campaign_not_found')
    _apply_campaign_input(db, campaign, payload)
    db.commit()
    campaign = db.scalar(_campaign_query().where(Campaign.id == campaign_id))
    return _json({'ok': True, 'campaign': _campaign_json(campaign, admin=True)})


@router.post('/admin/campaigns/{campaign_id}/image')
async def admin_campaign_image(campaign_id: int, request: Request, image: UploadFile = File(...), convert_to_png: bool = Form(False), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail='campaign_not_found')
    raw_image = await image.read()
    normalized, absolute_path, relative_path, checksum, mime_type = prepare_campaign_image(settings.media_root, campaign_id, raw_image, convert_to_png=convert_to_png)
    old_path = settings.media_root / campaign.image_path if campaign.image_path else None
    persist_prepared_image(absolute_path, normalized, checksum)
    campaign.image_path = relative_path
    campaign.image_checksum = checksum
    campaign.image_mime_type = mime_type
    db.commit()
    if old_path is not None and old_path != absolute_path and old_path.is_file():
        old_path.unlink()
    return _json({'ok': True, 'imageUrl': f'/media/{relative_path}'})


@router.delete('/admin/campaigns/{campaign_id}/image')
def admin_campaign_image_delete(campaign_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail='campaign_not_found')
    image_path = settings.media_root / campaign.image_path if campaign.image_path else None
    campaign.image_path = None
    campaign.image_checksum = None
    campaign.image_mime_type = None
    db.commit()
    if image_path is not None and image_path.is_file():
        image_path.unlink()
    return _json({'ok': True})


@router.delete('/admin/campaigns/{campaign_id}')
def admin_campaign_delete(campaign_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail='campaign_not_found')
    image_path = settings.media_root / campaign.image_path if campaign.image_path else None
    db.delete(campaign)
    db.commit()
    if image_path is not None and image_path.is_file():
        image_path.unlink()
    return _json({'ok': True})


@router.get('/admin/gift-promotions')
def admin_gift_promotions(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    rows = list(db.scalars(_gift_promotion_query().order_by(desc(GiftPromotion.id))).unique().all())
    return _json({'promotions': [_gift_promotion_json(row) for row in rows]})


@router.post('/admin/gift-promotions')
def admin_gift_promotion_create(payload: GiftPromotionInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    initial_gift_ref = payload.tiers[0].gift_product_ref if payload.tiers else payload.gift_product_ref
    promotion = GiftPromotion(title=payload.title.strip(), catalog_slug=payload.catalog_slug, gift_product_ref=initial_gift_ref or '')
    db.add(promotion)
    _apply_gift_promotion_input(db, promotion, payload)
    db.commit()
    promotion = db.scalar(_gift_promotion_query().where(GiftPromotion.id == promotion.id))
    return _json({'ok': True, 'promotion': _gift_promotion_json(promotion)}, 201)


@router.put('/admin/gift-promotions/{promotion_id}')
def admin_gift_promotion_update(promotion_id: int, payload: GiftPromotionInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    promotion = db.scalar(_gift_promotion_query().where(GiftPromotion.id == promotion_id))
    if promotion is None:
        raise HTTPException(status_code=404, detail='gift_promotion_not_found')
    _apply_gift_promotion_input(db, promotion, payload)
    db.commit()
    promotion = db.scalar(_gift_promotion_query().where(GiftPromotion.id == promotion_id))
    return _json({'ok': True, 'promotion': _gift_promotion_json(promotion)})


@router.delete('/admin/gift-promotions/{promotion_id}')
def admin_gift_promotion_delete(promotion_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    promotion = db.get(GiftPromotion, promotion_id)
    if promotion is None:
        raise HTTPException(status_code=404, detail='gift_promotion_not_found')
    db.delete(promotion)
    db.commit()
    return _json({'ok': True})


@router.get('/admin/catalogs')
def admin_catalogs(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _ensure_system_catalogs(db)
    product_counts = dict(db.execute(select(Product.catalog_slug, func.count(Product.ref)).group_by(Product.catalog_slug)).all())
    category_counts = dict(db.execute(select(Category.catalog_slug, func.count(Category.slug)).group_by(Category.catalog_slug)).all())
    return _json({'catalogs': [{**_catalog_json(item), 'productCount': int(product_counts.get(item.slug, 0)), 'categoryCount': int(category_counts.get(item.slug, 0))} for item in catalog_service.list_catalogs(db, include_inactive=True)]})


@router.post('/admin/catalogs')
def admin_catalog_create(payload: CatalogInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    slug = _catalog_slug(payload.slug or payload.label)
    if db.get(Catalog, slug) is not None:
        raise HTTPException(status_code=409, detail='catalog_already_exists')
    minimum = _decimal_3(payload.minimum_total, default=Decimal('0.00'))
    catalog = Catalog(slug=slug, label=payload.label.strip(), description=(payload.description or '').strip() or None, icon=payload.icon.strip() or 'mdi-bookshelf', minimum_total=minimum, sort_order=payload.sort_order, active=payload.active)
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return _json({'ok': True, 'catalog': _catalog_json(catalog)}, 201)


@router.put('/admin/catalogs/{slug}')
def admin_catalog_update(slug: str, payload: CatalogInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    catalog = db.get(Catalog, _catalog_slug(slug))
    if catalog is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    catalog.label = payload.label.strip()
    catalog.description = (payload.description or '').strip() or None
    catalog.icon = payload.icon.strip() or 'mdi-bookshelf'
    catalog.minimum_total = _decimal_3(payload.minimum_total, default=Decimal('0.00'))
    catalog.sort_order = payload.sort_order
    catalog.active = payload.active
    db.commit()
    db.refresh(catalog)
    return _json({'ok': True, 'catalog': _catalog_json(catalog)})


@router.delete('/admin/catalogs/{slug}')
def admin_catalog_delete(slug: str, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    normalized_slug = _catalog_slug(slug)
    if normalized_slug in {'villas', 'interpilhas'}:
        raise HTTPException(status_code=409, detail='system_catalog_protected')
    catalog = db.get(Catalog, normalized_slug)
    if catalog is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    product_count = int(db.scalar(select(func.count(Product.ref)).where(Product.catalog_slug == normalized_slug)) or 0)
    if product_count:
        raise HTTPException(status_code=409, detail='catalog_has_products')
    categories = list(db.scalars(select(Category).where(Category.catalog_slug == normalized_slug)).all())
    for category in sorted(categories, key=lambda item: item.parent_slug is None):
        db.delete(category)
    db.delete(catalog)
    db.commit()
    return _json({'ok': True, 'deletedCategories': len(categories)})


@router.get('/admin/import/products/template.xlsx')
def product_import_template(user: User = Depends(_api_admin)):
    path = Path(__file__).resolve().parents[1] / 'static' / 'templates' / 'modelo-importacao-produtos.xlsx'
    if not path.exists():
        raise HTTPException(status_code=404, detail='template_not_found')
    return FileResponse(path, filename='modelo-importacao-produtos.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _decimal_3(value: str | Decimal | None, *, default: Decimal | None = None) -> Decimal | None:
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail='invalid_decimal_value') from exc


def _ensure_system_catalog(db: Session, slug: str) -> Catalog | None:
    catalog = db.get(Catalog, slug)
    if catalog is not None:
        return catalog
    defaults = {
        'villas': ('Villas', 'Catálogo têxtil Villas.', 'mdi-hanger', 0, Decimal('250.00')),
        'interpilhas': ('Interpilhas', 'Pilhas, ambientadores, colas e adesivos.', 'mdi-battery-charging-medium', 10, Decimal('300.00')),
    }
    values = defaults.get(slug)
    if values is None:
        return None
    label, description, icon, sort_order, minimum_total = values
    catalog = Catalog(slug=slug, label=label, description=description, icon=icon, sort_order=sort_order, minimum_total=minimum_total, active=True)
    db.add(catalog)
    db.flush()
    return catalog


def _ensure_system_catalogs(db: Session) -> None:
    missing = any(db.get(Catalog, slug) is None for slug in ('villas', 'interpilhas'))
    if not missing:
        return
    _ensure_system_catalog(db, 'villas')
    _ensure_system_catalog(db, 'interpilhas')
    db.commit()


def _save_product_input(db: Session, payload: ProductInput, product: Product | None = None, *, commit: bool = True) -> Product:
    ref = normalize_reference(payload.ref)
    if not ref or not payload.name.strip() or not payload.product_type.strip():
        raise HTTPException(status_code=400, detail='product_required_fields')
    catalog_slug = normalize_reference(payload.catalog_slug).casefold() or 'villas'
    _ensure_system_catalogs(db)
    catalog = db.get(Catalog, catalog_slug)
    if catalog is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    category = db.get(Category, payload.category_slug) if payload.category_slug else None
    if payload.category_slug and category is None:
        raise HTTPException(status_code=404, detail='category_not_found')
    if category is not None and category.catalog_slug != catalog_slug:
        raise HTTPException(status_code=409, detail='category_catalog_mismatch')
    if payload.active and category is not None and not category.active:
        raise HTTPException(status_code=409, detail='category_inactive')
    if payload.active and category is not None and category.parent is not None and not category.parent.active:
        raise HTTPException(status_code=409, detail='category_parent_inactive')
    target = product or db.get(Product, ref)
    if target is None:
        target = Product(ref=ref)
        db.add(target)
    elif product is None:
        raise HTTPException(status_code=409, detail='ref_exists')
    target.catalog_slug = catalog_slug
    target.name = payload.name.strip()
    target.product_type = payload.product_type.strip()
    target.category_slug = payload.category_slug or None
    target.brand = (payload.brand or '').strip() or None
    target.family = (payload.family or '').strip() or None
    target.ean = (payload.ean or '').strip() or None
    target.price = _decimal_3(payload.price, default=Decimal('0.000')) or Decimal('0.000')
    target.price_base = _decimal_3(payload.price_base)
    target.eco_value = _decimal_3(payload.eco_value, default=Decimal('0.000')) or Decimal('0.000')
    target.pvp = None if payload.pvp in (None, '') else to_decimal(payload.pvp)
    target.case_inner = payload.case_inner
    target.case_outer = payload.case_outer
    target.colors_json = split_csv_values(payload.colors)
    target.sizes_json = split_csv_values(payload.sizes)
    target.season = normalize_season(payload.season)
    target.quantity_step = payload.quantity_step
    metadata = dict(target.metadata_json or {})
    metadata['quick_quantities'] = sorted({int(value) for value in payload.quick_quantities if int(value) > 0})[:4]
    target.metadata_json = metadata
    target.sort_order = payload.sort_order
    target.active = payload.active
    target.manual_active = payload.manual_active
    target.gift_only = payload.gift_only
    target.description = (payload.description or '').strip() or None
    if commit:
        db.commit()
        db.refresh(target)
    else:
        db.flush()
    return target


def _product_import_state(product: Product | None) -> dict[str, Any] | None:
    if product is None:
        return None
    return {
        'ref': product.ref, 'catalog_slug': product.catalog_slug, 'name': product.name, 'product_type': product.product_type,
        'category_slug': product.category_slug, 'brand': product.brand, 'family': product.family, 'ean': product.ean,
        'price': str(product.price), 'price_base': str(product.price_base) if product.price_base is not None else None,
        'eco_value': str(product.eco_value), 'pvp': str(product.pvp) if product.pvp is not None else None,
        'case_inner': product.case_inner, 'case_outer': product.case_outer, 'colors_json': list(product.colors_json or []),
        'sizes_json': list(product.sizes_json or []), 'sort_order': int(product.sort_order or 0), 'active': bool(product.active),
        'manual_active': bool(product.manual_active), 'season': product.season, 'quantity_step': int(product.quantity_step or 1),
        'description': product.description, 'metadata_json': dict(product.metadata_json or {}), 'gift_only': bool(product.gift_only),
    }


def _restore_product_import_state(product: Product, state: dict[str, Any]) -> None:
    for key in ('catalog_slug', 'name', 'product_type', 'category_slug', 'brand', 'family', 'ean', 'case_inner', 'case_outer', 'sort_order', 'active', 'manual_active', 'season', 'quantity_step', 'description', 'gift_only'):
        setattr(product, key, state.get(key))
    product.price = Decimal(state['price'])
    product.price_base = Decimal(state['price_base']) if state.get('price_base') is not None else None
    product.eco_value = Decimal(state.get('eco_value') or '0')
    product.pvp = Decimal(state['pvp']) if state.get('pvp') is not None else None
    product.colors_json = list(state.get('colors_json') or [])
    product.sizes_json = list(state.get('sizes_json') or [])
    product.metadata_json = dict(state.get('metadata_json') or {})


def _product_import_batch_json(batch: ProductImportBatch) -> dict[str, Any]:
    return {
        'id': batch.id, 'filename': batch.filename, 'sourceType': batch.source_type, 'catalog': batch.catalog_slug,
        'actor': batch.actor_username, 'created': batch.created_count, 'updated': batch.updated_count,
        'skipped': batch.skipped_count, 'status': batch.status, 'createdAt': batch.created_at,
        'rolledBackAt': batch.rolled_back_at, 'rollbackSummary': dict(batch.rollback_summary_json or {}),
        'changeCount': len(batch.changes_json or []), 'categoryCount': len(batch.created_categories_json or []),
    }


@router.post('/admin/products')
def product_create(payload: ProductInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'ok': True, 'product': _product_json(_save_product_input(db, payload))}, 201)


@router.put('/admin/products/{ref}')
def product_update(ref: str, payload: ProductInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    if normalize_reference(payload.ref) != product.ref:
        raise HTTPException(status_code=409, detail='ref_change_not_supported')
    return _json({'ok': True, 'product': _product_json(_save_product_input(db, payload, product))})


@router.post('/admin/products/save')
async def product_save_transaction(
    request: Request,
    payload_json: str = Form(..., alias='payload'),
    original_ref: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    _csrf(request)
    try:
        payload = ProductInput.model_validate_json(payload_json)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail='invalid_product_payload') from exc

    prepared = None
    if image is not None and image.filename:
        raw_image = await image.read()
        prepared = prepare_product_image(settings.media_root, payload.ref, raw_image)

    normalized_ref = normalize_reference(payload.ref)
    product = None
    if original_ref:
        product = db.get(Product, normalize_reference(original_ref))
        if product is None:
            raise HTTPException(status_code=404, detail='product_not_found')
        if normalized_ref != product.ref:
            raise HTTPException(status_code=409, detail='ref_change_not_supported')

    created_file = False
    absolute_path: Any = None
    try:
        saved = _save_product_input(db, payload, product, commit=False)
        if prepared is not None:
            normalized, absolute_path, relative_path, checksum, mime_type = prepared
            created_file = persist_prepared_image(absolute_path, normalized, checksum)
            saved.image_path = relative_path
            saved.image_checksum = checksum
            saved.image_mime_type = mime_type
            metadata = dict(saved.metadata_json or {})
            metadata.update({'image_zoom': calculate_image_zoom(normalized), 'image_framing_version': 1})
            saved.metadata_json = metadata
        db.commit()
        db.refresh(saved)
        return _json({'ok': True, 'product': _product_json(saved)}, 200 if original_ref else 201)
    except Exception:
        db.rollback()
        if created_file and absolute_path is not None and absolute_path.exists():
            absolute_path.unlink()
        raise


@router.post('/admin/import/products/preview')
async def product_import_preview(
    request: Request,
    catalog: str = Form(...),
    category_label: str = Form(''),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    _csrf(request)
    catalog_slug = normalize_reference(catalog).casefold()
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    try:
        parsed = parse_product_file(await file.read(), file.filename or '', catalog_slug, category_label=category_label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    categories = list(db.execute(select(Category).where(Category.catalog_slug == catalog_slug)).scalars().all())
    category_map: dict[str, Category] = {}
    for category in sorted(categories, key=lambda item: (item.parent_slug is not None, item.sort_order, item.label)):
        category_map.setdefault(import_match_key(category.label), category)
        category_map.setdefault(import_match_key(category.slug), category)

    preview_rows: list[dict[str, Any]] = []
    errors = list(parsed['errors'])
    warnings: list[dict[str, Any]] = []
    new_categories: dict[str, CategoryInput] = {}

    def resolve_category(label: str, parent_slug: str | None = None) -> tuple[str | None, str]:
        key = import_match_key(label)
        category = category_map.get(key) if key else None
        if category is not None:
            return category.slug, category.label
        if not label:
            return None, ''
        base = _catalog_slug(f'{catalog_slug}-{label}')
        slug = base
        suffix = 2
        occupied = {item.slug for item in categories} | set(new_categories)
        while slug in occupied and (slug not in new_categories or new_categories[slug].label != label):
            slug = f'{base[:75]}-{suffix}'
            suffix += 1
        if slug not in new_categories:
            new_categories[slug] = CategoryInput(slug=slug, catalog_slug=catalog_slug, parent_slug=parent_slug, label=label, sort_order=len(categories) + len(new_categories), active=True)
        return slug, label

    for raw in parsed['rows']:
        row = dict(raw)
        source_row = row.pop('source_row')
        category_label = row.pop('category_label', '')
        parent_label = row.pop('parent_category_label', '')
        parent_slug, _ = resolve_category(parent_label) if parent_label else (None, '')
        category_slug, resolved_label = resolve_category(category_label, parent_slug)
        if not category_label:
            warnings.append({'row': source_row, 'ref': row['ref'], 'message': 'Produto sem categoria'})
        row['category_slug'] = category_slug
        try:
            payload = ProductInput.model_validate(row)
        except ValidationError as exc:
            errors.append({'row': source_row, 'ref': row.get('ref', ''), 'messages': ['Dados inválidos nesta linha']})
            continue
        existing = db.get(Product, normalize_reference(payload.ref))
        preview_rows.append({
            'sourceRow': source_row,
            'status': 'update' if existing else 'create',
            'categoryLabel': resolved_label,
            'payload': payload.model_dump(),
        })
    return _json({
        'filename': file.filename or '',
        'sheet': parsed['sheet'],
        'sourceType': parsed.get('source_type', 'spreadsheet'),
        'headers': parsed['headers'],
        'rows': preview_rows,
        'errors': errors,
        'warnings': warnings,
        'categories': [item.model_dump() for item in new_categories.values()],
        'summary': {
            'valid': len(preview_rows),
            'create': sum(row['status'] == 'create' for row in preview_rows),
            'update': sum(row['status'] == 'update' for row in preview_rows),
            'errors': len(errors),
            'warnings': len(warnings),
        },
    })


@router.post('/admin/import/products/commit')
def product_import_commit(payload: ProductImportCommitInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    created = 0
    updated = 0
    skipped = 0
    changes: list[dict[str, Any]] = []
    created_categories: list[str] = []
    try:
        for category_input in sorted(payload.categories, key=lambda item: item.parent_slug is not None):
            if db.get(Category, category_input.slug) is None:
                if db.get(Catalog, category_input.catalog_slug) is None:
                    raise HTTPException(status_code=400, detail='catalog_not_found')
                db.add(Category(**category_input.model_dump()))
                created_categories.append(category_input.slug)
        db.flush()
        for row in payload.rows:
            ref = normalize_reference(row.ref)
            existing = db.get(Product, ref)
            if existing is not None and not payload.update_existing:
                skipped += 1
                continue
            before = _product_import_state(existing)
            saved = _save_product_input(db, row, existing, commit=False)
            changes.append({'ref': ref, 'before': before, 'after': _product_import_state(saved)})
            if existing is None:
                created += 1
            else:
                updated += 1
        batch = ProductImportBatch(
            actor_user_id=user.id,
            actor_username=user.username,
            catalog_slug=normalize_reference(payload.catalog).casefold() or (payload.rows[0].catalog_slug if payload.rows else 'villas'),
            filename=payload.filename.strip() or 'importacao',
            source_type=payload.source_type,
            created_count=created,
            updated_count=updated,
            skipped_count=skipped,
            changes_json=changes,
            created_categories_json=created_categories,
            status='applied',
            rollback_summary_json={},
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
    except Exception:
        db.rollback()
        raise
    return _json({'ok': True, 'created': created, 'updated': updated, 'skipped': skipped, 'total': created + updated, 'batch': _product_import_batch_json(batch)})


@router.get('/admin/import/products/history')
def product_import_history(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    batches = db.scalars(select(ProductImportBatch).order_by(desc(ProductImportBatch.created_at), desc(ProductImportBatch.id)).limit(100)).all()
    return _json({'batches': [_product_import_batch_json(batch) for batch in batches]})


@router.post('/admin/import/products/history/{batch_id}/rollback')
def product_import_rollback(batch_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    batch = db.get(ProductImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail='import_batch_not_found')
    if batch.status != 'applied':
        raise HTTPException(status_code=409, detail='import_batch_already_rolled_back')
    restored = 0
    removed = 0
    conflicts: list[str] = []
    for change in reversed(list(batch.changes_json or [])):
        ref = normalize_reference(change.get('ref'))
        product = db.get(Product, ref)
        before = change.get('before')
        after = change.get('after')
        if product is None or _product_import_state(product) != after:
            conflicts.append(ref)
            continue
        if before is None:
            used = bool(db.scalar(select(func.count(OrderLine.id)).where(OrderLine.product_ref == ref))) or bool(db.scalar(select(func.count(CartItem.id)).where(CartItem.product_ref == ref)))
            linked = (
                bool(db.scalar(select(func.count(CampaignProduct.id)).where(CampaignProduct.product_ref == ref)))
                or bool(db.scalar(select(func.count(GiftPromotionProduct.product_ref)).where(GiftPromotionProduct.product_ref == ref)))
                or bool(db.scalar(select(func.count(GiftPromotion.id)).where(GiftPromotion.gift_product_ref == ref)))
            )
            if used or linked:
                conflicts.append(ref)
                continue
            db.delete(product)
            removed += 1
        else:
            _restore_product_import_state(product, before)
            restored += 1
    db.flush()
    categories_removed = 0
    for slug in reversed(list(batch.created_categories_json or [])):
        category = db.get(Category, slug)
        if category is None:
            continue
        product_count = db.scalar(select(func.count(Product.ref)).where(Product.category_slug == slug)) or 0
        child_count = db.scalar(select(func.count(Category.slug)).where(Category.parent_slug == slug)) or 0
        if not product_count and not child_count:
            db.delete(category)
            categories_removed += 1
    summary = {'restored': restored, 'removed': removed, 'categoriesRemoved': categories_removed, 'conflicts': conflicts}
    batch.status = 'rolled_back' if not conflicts else 'rolled_back_with_conflicts'
    batch.rollback_summary_json = summary
    batch.rolled_back_at = utcnow()
    batch.rolled_back_by_user_id = user.id
    db.commit()
    return _json({'ok': True, 'batch': _product_import_batch_json(batch), **summary})


@router.post('/admin/import/products/pdf-images/preview')
async def product_pdf_images_preview(
    request: Request,
    catalog: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    _csrf(request)
    catalog_slug = normalize_reference(catalog).casefold()
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    rows, issues = parse_pdf_product_images(await file.read())
    refs = [row.ref for row in rows]
    products = list(db.scalars(select(Product).where(Product.ref.in_(refs))).all()) if refs else []
    product_map = {product.ref: product for product in products}
    result = []
    for row in rows:
        product = product_map.get(row.ref)
        matched = bool(product is not None and product.catalog_slug == catalog_slug)
        result.append({
            'ref': row.ref,
            'page': row.page,
            'sourceImages': row.source_images,
            'matched': matched,
            'productName': product.name if matched else '',
            'hasExistingImage': bool(product.image_path) if matched else False,
        })
    return _json({
        'filename': file.filename or '',
        'rows': result,
        'issues': issues,
        'summary': {
            'detected': len(rows),
            'matched': sum(row['matched'] for row in result),
            'missing': sum(not row['matched'] for row in result),
            'withExistingImage': sum(row['hasExistingImage'] for row in result),
        },
    })


@router.post('/admin/import/products/pdf-images/commit')
async def product_pdf_images_commit(
    request: Request,
    catalog: str = Form(...),
    overwrite: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    _csrf(request)
    catalog_slug = normalize_reference(catalog).casefold()
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    rows, issues = parse_pdf_product_images(await file.read())
    if issues:
        raise HTTPException(status_code=400, detail={'code': 'pdf_image_mapping_uncertain', 'issues': issues})
    refs = [row.ref for row in rows]
    products = list(db.scalars(select(Product).where(Product.ref.in_(refs), Product.catalog_slug == catalog_slug)).all()) if refs else []
    product_map = {product.ref: product for product in products}
    updated = 0
    skipped = 0
    missing = 0
    created_files: list[Path] = []
    try:
        for row in rows:
            product = product_map.get(row.ref)
            if product is None:
                missing += 1
                continue
            if product.image_path and not overwrite:
                skipped += 1
                continue
            normalized, absolute_path, relative_path, checksum, mime_type = prepare_product_image(settings.media_root, product.ref, row.image_bytes)
            if persist_prepared_image(absolute_path, normalized, checksum):
                created_files.append(absolute_path)
            product.image_path = relative_path
            product.image_checksum = checksum
            product.image_mime_type = mime_type
            metadata = dict(product.metadata_json or {})
            metadata.update({'image_zoom': calculate_image_zoom(normalized), 'image_framing_version': 1})
            product.metadata_json = metadata
            updated += 1
        db.commit()
    except Exception:
        db.rollback()
        for path in created_files:
            if path.exists():
                path.unlink()
        raise
    return _json({'ok': True, 'updated': updated, 'skipped': skipped, 'missing': missing, 'detected': len(rows)})


@router.get('/admin/audit-log')
def admin_audit_log(
    q: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    stmt = select(AdminAuditLog)
    if q:
        pattern = f'%{q.strip()}%'
        stmt = stmt.where(or_(AdminAuditLog.actor_username.like(pattern), AdminAuditLog.entity_id.like(pattern), AdminAuditLog.route.like(pattern)))
    if action:
        stmt = stmt.where(AdminAuditLog.action == action.strip().casefold())
    if entity_type:
        stmt = stmt.where(AdminAuditLog.entity_type == entity_type.strip().casefold())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.execute(stmt.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id)).offset((page - 1) * per_page).limit(per_page)).scalars().all())
    return _json({
        'items': [{
            'id': row.id,
            'actor': row.actor_username,
            'action': row.action,
            'entityType': row.entity_type,
            'entityId': row.entity_id,
            'route': row.route,
            'requestId': row.request_id,
            'statusCode': row.status_code,
            'createdAt': row.created_at,
        } for row in rows],
        'total': total,
        'page': page,
        'pages': max(1, (total + per_page - 1) // per_page),
    })


@router.post('/admin/products/{ref}/image')
async def product_image(ref: str, request: Request, image: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    image_path, checksum, mime_type, image_zoom = await save_uploaded_product_image(image, settings.media_root, product.ref)
    product.image_path = image_path
    product.image_checksum = checksum
    product.image_mime_type = mime_type
    metadata = dict(product.metadata_json or {})
    metadata.update({'image_zoom': image_zoom, 'image_framing_version': 1})
    product.metadata_json = metadata
    db.commit()
    db.refresh(product)
    return _json({'ok': True, 'product': _product_json(product)})


@router.patch('/admin/products/{ref}/active')
def product_active(ref: str, payload: ActiveInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    if payload.active and product.category_slug:
        category = db.get(Category, product.category_slug)
        if category is not None and not category.active:
            raise HTTPException(status_code=409, detail='category_inactive')
        if category is not None and category.parent is not None and not category.parent.active:
            raise HTTPException(status_code=409, detail='category_parent_inactive')
    product.active = payload.active
    db.commit()
    return _json({'ok': True, 'product': _product_json(product)})


@router.delete('/admin/products/{ref}')
def product_delete(ref: str, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    if product.order_lines or product.cart_items:
        raise HTTPException(status_code=409, detail='product_in_use')
    image_path = settings.media_root / product.image_path if product.image_path else None
    db.delete(product)
    db.commit()
    if image_path is not None and image_path.is_file():
        image_path.unlink()
    return _json({'ok': True})


@router.post('/admin/categories')
def category_save(payload: CategoryInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    slug = normalize_reference(payload.slug)
    if not slug or not payload.label.strip():
        raise HTTPException(status_code=400, detail='category_required_fields')
    catalog_slug = normalize_reference(payload.catalog_slug).casefold() or 'villas'
    _ensure_system_catalogs(db)
    if db.get(Catalog, catalog_slug) is None:
        raise HTTPException(status_code=404, detail='catalog_not_found')
    parent_slug = normalize_reference(payload.parent_slug) or None
    if parent_slug == slug:
        raise HTTPException(status_code=409, detail='category_parent_self')
    parent = db.get(Category, parent_slug) if parent_slug else None
    if parent_slug and parent is None:
        raise HTTPException(status_code=404, detail='category_parent_not_found')
    if parent is not None and parent.catalog_slug != catalog_slug:
        raise HTTPException(status_code=409, detail='category_catalog_mismatch')
    if parent is not None and parent.parent_slug is not None:
        raise HTTPException(status_code=409, detail='category_depth_exceeded')
    category = db.get(Category, slug) or Category(slug=slug, catalog_slug=catalog_slug)
    if category not in db:
        db.add(category)
    category.catalog_slug = catalog_slug
    category.parent_slug = parent_slug
    category.label = payload.label.strip()
    category.icon = payload.icon.strip() if payload.icon else None
    category.sort_order = payload.sort_order
    category.active = payload.active
    category.visible_on_site = payload.active
    db.commit()
    db.refresh(category)
    return _json({'ok': True, 'category': _category_json(category)})


@router.delete('/admin/categories/{slug}')
def category_delete(slug: str, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    category = db.get(Category, normalize_reference(slug))
    if category is None:
        raise HTTPException(status_code=404, detail='category_not_found')
    children = list(db.scalars(select(Category).where(Category.parent_slug == category.slug)).all())
    removed_slugs = [category.slug, *(child.slug for child in children)]
    products = list(db.scalars(select(Product).where(Product.category_slug.in_(removed_slugs))).all())
    for product in products:
        product.category_slug = None
    for child in children:
        db.delete(child)
    db.delete(category)
    db.commit()
    return _json({'ok': True, 'unassignedProducts': len(products), 'deletedChildren': len(children)})


@router.get('/admin/warnings')
def warnings_get(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json({'warnings': [asdict(item) for item in warning_service.list_warnings(db)]})


@router.post('/admin/warnings/{warning_key}/ignore')
def warning_ignore(warning_key: str, payload: WarningIgnoreInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    warning_service.ignore_warning(db, warning_key=warning_key, ignored_by_user_id=user.id, reason=payload.reason)
    return _json({'ok': True})


@router.post('/admin/warnings/ignore-all')
def warnings_ignore_all(payload: WarningIgnoreInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'ok': True, 'ignored': warning_service.ignore_all_warnings(db, ignored_by_user_id=user.id, reason=payload.reason)})


@router.get('/admin/statistics')
def statistics_get(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    scope: str = Query(default='month', pattern='^(month|year)$'),
    catalog: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_api_admin),
):
    if year is None or month is None:
        current_period = _business_now()
        year = year or current_period.year
        month = month or current_period.month
    catalog_value = normalize_reference(catalog).casefold() if catalog else None
    if catalog_value is not None and db.get(Catalog, catalog_value) is None:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    if scope == 'year':
        report = stats_service.annual_report(db, year=year, catalog=catalog_value)
        insights = stats_service.year_insights(db, year=year, catalog=catalog_value)
        detail = stats_service.year_detail(db, year=year, catalog=catalog_value)
    else:
        report = stats_service.monthly_report(db, year=year, month=month, catalog=catalog_value)
        insights = stats_service.period_insights(db, year=year, month=month, catalog=catalog_value)
        detail = stats_service.period_detail(db, year=year, month=month, catalog=catalog_value)
    return _json({
        'scope': scope,
        'catalog': catalog_value or 'all',
        'report': asdict(report),
        'series': [asdict(item) for item in stats_service.monthly_series(db, months=24, catalog=catalog_value)],
        'insights': insights,
        'detail': detail,
    })


@router.get('/admin/order-draft')
def draft_get(db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json({'draft': asdict(draft_service.get_active_draft(db, user.id))})


@router.patch('/admin/order-draft/customer')
def draft_customer(payload: DraftCustomerInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.set_customer(db, admin_user_id=user.id, customer_user_id=payload.customer_id))})


@router.post('/admin/order-draft/lines')
def draft_line(payload: DraftLineInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.add_line(db, admin_user_id=user.id, ref=payload.ref, color=payload.color, size=payload.size, quantity=payload.quantity))})


@router.delete('/admin/order-draft/lines/{line_id}')
def draft_line_delete(line_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.remove_line(db, admin_user_id=user.id, line_id=line_id))})


@router.patch('/admin/order-draft/notes')
def draft_notes(payload: DraftNotesInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.set_notes(db, admin_user_id=user.id, notes=payload.notes, pdf_notes=payload.pdf_notes, include_pdf_notes=payload.include_pdf_notes))})


@router.delete('/admin/order-draft')
def draft_clear(request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.clear(db, admin_user_id=user.id))})


@router.post('/admin/order-draft/submit')
def draft_submit(request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = draft_service.submit(db, admin_user_id=user.id, request_id=getattr(request.state, 'request_id', None))
    EmailService().send_order_event(db, order=order, event='order_confirmed', request_id=getattr(request.state, 'request_id', None), related_user_id=order['userId'])
    return _json({'ok': True, 'order': order}, 201)
