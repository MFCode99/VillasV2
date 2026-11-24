from __future__ import annotations

import zipfile
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from typing import Any, Iterable
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as xml_escape

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .catalog import normalize_choice_text, normalize_qty_step, normalize_reference, normalize_text, split_csv_values, to_decimal
from .config import get_settings
from .models import (
    AdminOrderDraft,
    AdminOrderDraftLine,
    AdminWarningIgnore,
    Catalog,
    Category,
    Order,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
    Product,
    User,
)
from .order_service import OrderService
from .security import public_order_number, utcnow


MONEY = Decimal('0.01')
UNIT_PRICE = Decimal('0.001')


def _money(value: Any) -> Decimal:
    return to_decimal(value, Decimal('0.00')).quantize(MONEY)


def _unit_price(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(UNIT_PRICE)


def _safe_excel_text(value: Any) -> str:
    text = normalize_text(str(value) if value is not None else '')
    if text[:1] in {'=', '+', '-', '@'}:
        return "'" + text
    return text


def _business_tz() -> ZoneInfo | timezone:
    settings = get_settings()
    configured = getattr(settings, 'business_timezone', 'Europe/Lisbon') or 'Europe/Lisbon'
    try:
        return ZoneInfo(configured)
    except Exception:
        try:
            return ZoneInfo('Europe/Lisbon')
        except Exception:
            return timezone.utc


def _as_business_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(_business_tz()).replace(tzinfo=None)


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _confirmed_at(order: Order) -> datetime | None:
    if order.confirmed_at:
        return order.confirmed_at
    for history in sorted(list(order.history or []), key=lambda row: (row.changed_at, row.id)):
        if normalize_text(history.new_status).casefold() == OrderStatus.CONFIRMED.value:
            return history.changed_at
    return None


def _shipped_at(order: Order) -> datetime | None:
    for history in sorted(list(order.history or []), key=lambda row: (row.changed_at, row.id)):
        if normalize_text(history.new_status).casefold() == OrderStatus.SHIPPED.value:
            return history.changed_at
    return None


def _created_at(order: Order) -> datetime:
    return order.created_at or utcnow()


@dataclass(slots=True)
class DashboardMetrics:
    pending_orders: int
    confirmed_orders: int
    shipped_orders: int
    total_clients: int
    today_confirmed_revenue: Decimal
    today_confirmed_units: int
    month_confirmed_revenue: Decimal
    month_confirmed_units: int
    previous_month_confirmed_revenue: Decimal
    previous_month_confirmed_units: int
    warning_count: int


@dataclass(slots=True)
class MonthlyReportRow:
    year: int
    month: int
    pending_orders: int
    confirmed_orders: int
    shipped_orders: int
    confirmed_revenue: Decimal
    confirmed_units: int


@dataclass(slots=True)
class AnnualReportRow:
    year: int
    pending_orders: int
    confirmed_orders: int
    shipped_orders: int
    confirmed_revenue: Decimal
    confirmed_units: int


@dataclass(slots=True)
class WarningItem:
    key: str
    warning_type: str
    entity_type: str
    entity_id: int
    title: str
    detail: str
    customer_name: str
    customer_company: str
    customer_email: str
    customer_nif: str
    customer_active: bool
    created_at: datetime


class AdminStatisticsService:
    def _orders_query(self):
        return select(Order).options(selectinload(Order.history), selectinload(Order.items).selectinload(OrderLine.product), selectinload(Order.user), selectinload(Order.created_by_user))

    @staticmethod
    def _order_catalog(order: Order) -> str:
        snapshot = dict(order.snapshot_json or {})
        if snapshot.get('catalog_slug'):
            return normalize_text(snapshot.get('catalog_slug')).casefold()
        for line in order.items:
            line_snapshot = dict(line.snapshot_json or {})
            if line_snapshot.get('catalog_slug'):
                return normalize_text(line_snapshot.get('catalog_slug')).casefold()
            if line.product is not None and line.product.catalog_slug:
                return normalize_text(line.product.catalog_slug).casefold()
        return 'villas'

    def _all_orders(self, db: Session, *, catalog: str | None = None) -> list[Order]:
        stmt = self._orders_query().order_by(desc(Order.created_at), desc(Order.id))
        orders = list(db.execute(stmt).scalars().unique().all())
        if catalog:
            catalog_value = normalize_text(catalog).casefold()
            orders = [order for order in orders if self._order_catalog(order) == catalog_value]
        return orders

    def _monthly_report_from_orders(self, orders: list[Order], *, year: int, month: int) -> MonthlyReportRow:
        start, end = _month_bounds(year, month)
        pending_orders = sum(1 for order in orders if order.order_status == OrderStatus.PENDING.value and start <= _as_business_time(_created_at(order)) < end)
        confirmed_orders = 0
        shipped_orders = 0
        confirmed_revenue = Decimal('0.00')
        confirmed_units = 0
        for order in orders:
            order_created_at = _as_business_time(_created_at(order))
            if order_created_at is None or not (start <= order_created_at < end):
                continue
            if order.order_status not in {OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value}:
                continue
            confirmed_orders += 1
            confirmed_revenue += _money(order.total)
            confirmed_units += int(order.units or 0)
            if order.order_status == OrderStatus.SHIPPED.value:
                shipped_orders += 1
        return MonthlyReportRow(
            year=year,
            month=month,
            pending_orders=pending_orders,
            confirmed_orders=confirmed_orders,
            shipped_orders=shipped_orders,
            confirmed_revenue=confirmed_revenue.quantize(MONEY),
            confirmed_units=confirmed_units,
        )

    def monthly_report(self, db: Session, *, year: int, month: int, catalog: str | None = None) -> MonthlyReportRow:
        return self._monthly_report_from_orders(self._all_orders(db, catalog=catalog), year=year, month=month)

    def dashboard_metrics(self, db: Session, *, catalog: str | None = None) -> DashboardMetrics:
        now = _as_business_time(utcnow()) or utcnow()
        current_month_start, current_month_end = _month_bounds(now.year, now.month)
        if now.month == 1:
            prev_year, prev_month = now.year - 1, 12
        else:
            prev_year, prev_month = now.year, now.month - 1
        prev_month_start, prev_month_end = _month_bounds(prev_year, prev_month)
        orders = self._all_orders(db, catalog=catalog)
        pending_orders = sum(1 for order in orders if order.order_status == OrderStatus.PENDING.value)
        confirmed_orders = sum(1 for order in orders if order.order_status == OrderStatus.CONFIRMED.value)
        shipped_orders = sum(1 for order in orders if order.order_status == OrderStatus.SHIPPED.value)
        total_clients = db.scalar(select(func.count(User.id)).where(User.role == 'client')) or 0
        warning_count = len(WarningService().list_warnings(db))

        today_start = datetime(now.year, now.month, now.day)
        tomorrow = today_start + timedelta(days=1)
        today_revenue = Decimal('0.00')
        today_units = 0
        month_revenue = Decimal('0.00')
        month_units = 0
        prev_revenue = Decimal('0.00')
        prev_units = 0
        for order in orders:
            if order.order_status not in {OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value}:
                continue
            order_created_at = _as_business_time(_created_at(order))
            if order_created_at is None:
                continue
            if today_start <= order_created_at < tomorrow:
                today_revenue += _money(order.total)
                today_units += int(order.units or 0)
            if current_month_start <= order_created_at < current_month_end:
                month_revenue += _money(order.total)
                month_units += int(order.units or 0)
            if prev_month_start <= order_created_at < prev_month_end:
                prev_revenue += _money(order.total)
                prev_units += int(order.units or 0)
        return DashboardMetrics(
            pending_orders=pending_orders,
            confirmed_orders=confirmed_orders,
            shipped_orders=shipped_orders,
            total_clients=total_clients,
            today_confirmed_revenue=today_revenue.quantize(MONEY),
            today_confirmed_units=today_units,
            month_confirmed_revenue=month_revenue.quantize(MONEY),
            month_confirmed_units=month_units,
            previous_month_confirmed_revenue=prev_revenue.quantize(MONEY),
            previous_month_confirmed_units=prev_units,
            warning_count=warning_count,
        )

    def status_breakdown(self, db: Session) -> dict[str, int]:
        orders = self._all_orders(db)
        return {
            'pending': sum(1 for order in orders if order.order_status == OrderStatus.PENDING.value),
            'confirmed': sum(1 for order in orders if order.order_status == OrderStatus.CONFIRMED.value),
            'shipped': sum(1 for order in orders if order.order_status == OrderStatus.SHIPPED.value),
        }

    def confirmed_revenue(self, db: Session) -> Decimal:
        orders = self._all_orders(db)
        revenue = Decimal('0.00')
        for order in orders:
            if order.order_status in {OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value}:
                revenue += _money(order.total)
        return revenue.quantize(MONEY)

    def monthly_series(self, db: Session, *, months: int = 12, catalog: str | None = None) -> list[MonthlyReportRow]:
        now = _as_business_time(utcnow()) or utcnow()
        orders = self._all_orders(db, catalog=catalog)
        rows: list[MonthlyReportRow] = []
        year = now.year
        month = now.month
        for _ in range(months):
            rows.append(self._monthly_report_from_orders(orders, year=year, month=month))
            if month == 1:
                year -= 1
                month = 12
            else:
                month -= 1
        return list(reversed(rows))

    def _range_insights(self, db: Session, *, start: datetime, end: datetime, catalog: str | None = None) -> dict[str, Any]:
        orders = [
            order for order in self._all_orders(db, catalog=catalog)
            if order.order_status in {OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value}
            and start <= (_as_business_time(_created_at(order)) or start) < end
        ]
        product_totals: dict[str, dict[str, Any]] = {}
        customer_totals: dict[int, dict[str, Any]] = {}
        for order in orders:
            customer = customer_totals.setdefault(order.user_id, {
                'id': order.user_id,
                'name': order.customer_name,
                'company': order.customer_company or '',
                'orders': 0,
                'revenue': Decimal('0.00'),
            })
            customer['orders'] += 1
            customer['revenue'] += _money(order.total)
            for line in order.items:
                product = product_totals.setdefault(line.product_ref, {
                    'ref': line.product_ref,
                    'name': line.product_name,
                    'units': 0,
                    'revenue': Decimal('0.00'),
                })
                product['units'] += int(line.quantity or 0)
                product['revenue'] += _money(line.line_total)
        revenue = sum((_money(order.total) for order in orders), Decimal('0.00'))
        top_products = sorted(product_totals.values(), key=lambda row: (-row['units'], -row['revenue'], row['ref']))[:8]
        top_customers = sorted(customer_totals.values(), key=lambda row: (-row['revenue'], -row['orders'], row['name']))[:8]
        return {
            'average_order_value': _money(revenue / len(orders)) if orders else Decimal('0.00'),
            'unique_customers': len(customer_totals),
            'top_products': top_products,
            'top_customers': top_customers,
        }

    def period_insights(self, db: Session, *, year: int, month: int, catalog: str | None = None) -> dict[str, Any]:
        start, end = _month_bounds(year, month)
        return self._range_insights(db, start=start, end=end, catalog=catalog)

    def year_insights(self, db: Session, *, year: int, catalog: str | None = None) -> dict[str, Any]:
        return self._range_insights(db, start=datetime(year, 1, 1), end=datetime(year + 1, 1, 1), catalog=catalog)

    def _range_detail(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        catalog: str | None = None,
        bucket: str = 'day',
    ) -> dict[str, Any]:
        orders = [
            order for order in self._all_orders(db, catalog=catalog)
            if start <= (_as_business_time(_created_at(order)) or start) < end
        ]
        catalogs = list(db.execute(select(Catalog).order_by(Catalog.sort_order, Catalog.label)).scalars().all())
        catalog_labels = {row.slug: row.label for row in catalogs}
        if bucket == 'month':
            buckets = {month: {'month': month, 'orders': 0, 'units': 0, 'revenue': Decimal('0.00')} for month in range(1, 13)}
        else:
            buckets = {
                day: {'day': day, 'orders': 0, 'units': 0, 'revenue': Decimal('0.00')}
                for day in range(1, monthrange(start.year, start.month)[1] + 1)
            }
        status_rows = {
            OrderStatus.PENDING.value: {'status': OrderStatus.PENDING.value, 'label': 'Pendentes', 'orders': 0, 'value': Decimal('0.00')},
            OrderStatus.CONFIRMED.value: {'status': OrderStatus.CONFIRMED.value, 'label': 'Confirmadas', 'orders': 0, 'value': Decimal('0.00')},
            OrderStatus.SHIPPED.value: {'status': OrderStatus.SHIPPED.value, 'label': 'Enviadas', 'orders': 0, 'value': Decimal('0.00')},
        }
        visible_catalogs = [row for row in catalogs if catalog is None or row.slug == catalog]
        catalog_rows: dict[str, dict[str, Any]] = {
            row.slug: {
                'slug': row.slug,
                'label': row.label,
                'active': bool(row.active),
                'orders': 0,
                'units': 0,
                'revenue': Decimal('0.00'),
            }
            for row in visible_catalogs
        }
        serialized_orders: list[dict[str, Any]] = []
        confirmed_revenue = Decimal('0.00')
        pending_value = Decimal('0.00')
        confirmed_units = 0
        confirmed_order_count = 0
        customer_ids: set[int] = set()
        for order in orders:
            created_at = _as_business_time(_created_at(order)) or start
            status_value = normalize_text(order.order_status).casefold()
            amount = _money(order.total)
            status_row = status_rows.get(status_value)
            if status_row is not None:
                status_row['orders'] += 1
                status_row['value'] += amount
            catalog_slug = self._order_catalog(order)
            snapshot = dict(order.snapshot_json or {})
            catalog_label = normalize_text(snapshot.get('catalog_label')) or catalog_labels.get(catalog_slug) or catalog_slug.replace('-', ' ').title()
            is_confirmed = status_value in {OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value}
            if is_confirmed:
                confirmed_order_count += 1
                confirmed_revenue += amount
                confirmed_units += int(order.units or 0)
                customer_ids.add(int(order.user_id))
                bucket_key = created_at.month if bucket == 'month' else created_at.day
                buckets[bucket_key]['orders'] += 1
                buckets[bucket_key]['units'] += int(order.units or 0)
                buckets[bucket_key]['revenue'] += amount
                catalog_row = catalog_rows.setdefault(catalog_slug, {
                    'slug': catalog_slug,
                    'label': catalog_label,
                    'active': False,
                    'orders': 0,
                    'units': 0,
                    'revenue': Decimal('0.00'),
                })
                catalog_row['orders'] += 1
                catalog_row['units'] += int(order.units or 0)
                catalog_row['revenue'] += amount
            elif status_value == OrderStatus.PENDING.value:
                pending_value += amount
            serialized_orders.append({
                'id': order.id,
                'publicNumber': order.public_number or public_order_number(created_at.year, order.id),
                'createdAt': created_at,
                'confirmedAt': _as_business_time(_confirmed_at(order)),
                'customerName': order.customer_name,
                'customerCompany': order.customer_company or '',
                'customerNif': order.customer_nif or '',
                'catalogSlug': catalog_slug,
                'catalogLabel': catalog_label,
                'orderStatus': status_value,
                'orderStatusLabel': status_rows.get(status_value, {}).get('label', status_value.title()),
                'units': int(order.units or 0),
                'subtotal': f'{_money(order.subtotal):.2f}',
                'total': f'{amount:.2f}',
                'origin': order.origin or 'client',
                'createdByUsername': order.created_by_user.username if order.created_by_user else '',
            })
        return {
            'orders_total': len(orders),
            'confirmed_orders': confirmed_order_count,
            'confirmed_revenue': confirmed_revenue.quantize(MONEY),
            'pending_value': pending_value.quantize(MONEY),
            'confirmed_units': confirmed_units,
            'unique_customers': len(customer_ids),
            'average_order_value': _money(confirmed_revenue / confirmed_order_count) if confirmed_order_count else Decimal('0.00'),
            'status_breakdown': list(status_rows.values()),
            'daily': list(buckets.values()) if bucket == 'day' else [],
            'months': list(buckets.values()) if bucket == 'month' else [],
            'catalog_breakdown': sorted(catalog_rows.values(), key=lambda row: (-row['revenue'], row['label'])),
            'orders': serialized_orders,
        }

    def period_detail(self, db: Session, *, year: int, month: int, catalog: str | None = None) -> dict[str, Any]:
        start, end = _month_bounds(year, month)
        return self._range_detail(db, start=start, end=end, catalog=catalog, bucket='day')

    def year_detail(self, db: Session, *, year: int, catalog: str | None = None) -> dict[str, Any]:
        return self._range_detail(
            db,
            start=datetime(year, 1, 1),
            end=datetime(year + 1, 1, 1),
            catalog=catalog,
            bucket='month',
        )

    def annual_report(self, db: Session, *, year: int, catalog: str | None = None) -> AnnualReportRow:
        detail = self.year_detail(db, year=year, catalog=catalog)
        status_rows = {row['status']: row for row in detail['status_breakdown']}
        return AnnualReportRow(
            year=year,
            pending_orders=int(status_rows[OrderStatus.PENDING.value]['orders']),
            confirmed_orders=int(detail['confirmed_orders']),
            shipped_orders=int(status_rows[OrderStatus.SHIPPED.value]['orders']),
            confirmed_revenue=_money(detail['confirmed_revenue']),
            confirmed_units=int(detail['confirmed_units']),
        )


class WarningService:
    warning_prefix = 'customer'

    def _ignore_rows(self, db: Session) -> dict[str, AdminWarningIgnore]:
        rows = list(db.execute(select(AdminWarningIgnore)).scalars().all())
        return {row.warning_key: row for row in rows}

    def _customer_warnings(self, customer: User) -> list[WarningItem]:
        items: list[WarningItem] = []
        base = f'{self.warning_prefix}_missing'
        if not normalize_text(getattr(customer, 'nif', None)):
            items.append(
                WarningItem(
                    key=f'{base}_nif:{customer.id}',
                    warning_type='missing_nif',
                    entity_type='user',
                    entity_id=customer.id,
                    title='NIF em falta',
                    detail='O cliente não tem NIF preenchido.',
                    customer_name=normalize_text(customer.full_name),
                    customer_company=normalize_text(customer.company_name),
                    customer_email=normalize_text(customer.email),
                    customer_nif=normalize_text(getattr(customer, 'nif', None)),
                    customer_active=bool(customer.active),
                    created_at=customer.created_at,
                )
            )
        if not normalize_text(customer.email):
            items.append(
                WarningItem(
                    key=f'{base}_email:{customer.id}',
                    warning_type='missing_email',
                    entity_type='user',
                    entity_id=customer.id,
                    title='Email em falta',
                    detail='O cliente não tem email preenchido.',
                    customer_name=normalize_text(customer.full_name),
                    customer_company=normalize_text(customer.company_name),
                    customer_email=normalize_text(customer.email),
                    customer_nif=normalize_text(getattr(customer, 'nif', None)),
                    customer_active=bool(customer.active),
                    created_at=customer.created_at,
                )
            )
        return items

    def list_warnings(self, db: Session) -> list[WarningItem]:
        ignored = self._ignore_rows(db)
        customers = list(
            db.execute(select(User).where(User.role == 'client').order_by(desc(User.created_at), desc(User.id))).scalars().all()
        )
        warnings: list[WarningItem] = []
        for customer in customers:
            for warning in self._customer_warnings(customer):
                if warning.key not in ignored:
                    warnings.append(warning)
        return warnings

    def count_warnings(self, db: Session) -> int:
        return len(self.list_warnings(db))

    def get_warning_by_key(self, db: Session, warning_key: str) -> WarningItem | None:
        for warning in self.list_warnings(db):
            if warning.key == warning_key:
                return warning
        return None

    def ignore_warning(self, db: Session, *, warning_key: str, ignored_by_user_id: int, reason: str | None = None) -> None:
        warning = self.get_warning_by_key(db, warning_key)
        if warning is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='warning_not_found')
        existing = db.scalar(select(AdminWarningIgnore).where(AdminWarningIgnore.warning_key == warning.key))
        if existing is None:
            db.add(
                AdminWarningIgnore(
                    warning_key=warning.key,
                    warning_type=warning.warning_type,
                    entity_type=warning.entity_type,
                    entity_id=warning.entity_id,
                    ignored_by_user_id=ignored_by_user_id,
                    ignored_at=utcnow(),
                    reason=normalize_text(reason) or None,
                )
            )
            db.commit()

    def ignore_all_warnings(self, db: Session, *, ignored_by_user_id: int, reason: str | None = None) -> int:
        warnings = self.list_warnings(db)
        if not warnings:
            return 0
        for warning in warnings:
            db.add(
                AdminWarningIgnore(
                    warning_key=warning.key,
                    warning_type=warning.warning_type,
                    entity_type=warning.entity_type,
                    entity_id=warning.entity_id,
                    ignored_by_user_id=ignored_by_user_id,
                    ignored_at=utcnow(),
                    reason=normalize_text(reason) or None,
                )
            )
        db.commit()
        return len(warnings)

    def customer_warning_keys(self, db: Session, customer_id: int) -> list[str]:
        customer = db.get(User, customer_id)
        if customer is None:
            return []
        return [warning.key for warning in self._customer_warnings(customer)]


@dataclass(slots=True)
class DraftLineData:
    line_id: int | None
    product_ref: str
    color: str
    size: str
    quantity: int
    product_name: str
    product_type: str
    unit_price: Decimal
    line_total: Decimal
    image_path: str | None


@dataclass(slots=True)
class DraftData:
    draft_id: int
    admin_user_id: int
    customer_user_id: int | None
    request_id: str
    notes: str | None
    pdf_notes: str | None
    include_pdf_notes: bool
    is_active: bool
    customer_name: str
    customer_company: str
    customer_email: str
    customer_nif: str
    lines: list[DraftLineData]
    subtotal: Decimal
    units: int
    lines_count: int


class AdminOrderDraftService:
    def _ensure_draft(self, db: Session, admin_user_id: int) -> AdminOrderDraft:
        draft = db.scalar(select(AdminOrderDraft).where(AdminOrderDraft.admin_user_id == admin_user_id, AdminOrderDraft.is_active.is_(True)).with_for_update())
        if draft is None:
            draft = AdminOrderDraft(
                admin_user_id=admin_user_id,
                customer_user_id=None,
                request_id=f'admin-draft-{admin_user_id}-{utcnow().strftime("%Y%m%d%H%M%S%f")}',
                is_active=True,
                notes=None,
                pdf_notes=None,
                include_pdf_notes=False,
                draft_snapshot_json={},
            )
            db.add(draft)
            db.flush()
        return draft

    def _serialize_line(self, line: AdminOrderDraftLine) -> DraftLineData:
        snapshot = dict(line.line_snapshot_json or {})
        return DraftLineData(
            line_id=line.id,
            product_ref=line.product_ref,
            color=normalize_choice_text(line.color),
            size=normalize_choice_text(line.size),
            quantity=int(line.quantity or 0),
            product_name=normalize_text(snapshot.get('product_name') or snapshot.get('name') or ''),
            product_type=normalize_text(snapshot.get('product_type') or snapshot.get('type') or ''),
            unit_price=_unit_price(snapshot.get('unit_price') or 0),
            line_total=_money(snapshot.get('line_total') or 0),
            image_path=snapshot.get('image_path'),
        )

    def _draft_query(self):
        return (
            select(AdminOrderDraft)
            .options(selectinload(AdminOrderDraft.lines))
            .where(AdminOrderDraft.is_active.is_(True))
        )

    def get_active_draft(self, db: Session, admin_user_id: int) -> DraftData:
        draft = db.scalar(
            select(AdminOrderDraft)
            .options(selectinload(AdminOrderDraft.lines), selectinload(AdminOrderDraft.customer_user))
            .where(AdminOrderDraft.admin_user_id == admin_user_id, AdminOrderDraft.is_active.is_(True))
        )
        if draft is None:
            draft = self._ensure_draft(db, admin_user_id)
            db.commit()
            db.refresh(draft)
            draft = db.scalar(
                select(AdminOrderDraft)
                .options(selectinload(AdminOrderDraft.lines), selectinload(AdminOrderDraft.customer_user))
                .where(AdminOrderDraft.id == draft.id)
            )
        assert draft is not None
        customer = draft.customer_user
        lines = [self._serialize_line(line) for line in sorted(list(draft.lines), key=lambda row: (row.id, row.product_ref, row.color, row.size))]
        subtotal = sum((line.line_total for line in lines), Decimal('0.00'))
        units = sum(line.quantity for line in lines)
        return DraftData(
            draft_id=draft.id,
            admin_user_id=draft.admin_user_id,
            customer_user_id=draft.customer_user_id,
            request_id=draft.request_id,
            notes=draft.notes,
            pdf_notes=draft.pdf_notes,
            include_pdf_notes=bool(draft.include_pdf_notes),
            is_active=bool(draft.is_active),
            customer_name=normalize_text(customer.full_name) if customer else '',
            customer_company=normalize_text(customer.company_name) if customer else '',
            customer_email=normalize_text(customer.email) if customer else '',
            customer_nif=normalize_text(getattr(customer, 'nif', None)) if customer else '',
            lines=lines,
            subtotal=_money(subtotal),
            units=units,
            lines_count=len(lines),
        )

    def set_customer(self, db: Session, *, admin_user_id: int, customer_user_id: int) -> DraftData:
        with db.begin():
            customer = db.get(User, customer_user_id)
            if customer is None or customer.role != 'client':
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='customer_not_found')
            if not customer.active:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='customer_inactive')
            draft = self._ensure_draft(db, admin_user_id)
            draft.customer_user_id = customer_user_id
            draft.draft_snapshot_json = {
                'customer_user_id': customer_user_id,
                'customer_name': customer.full_name,
                'customer_company': customer.company_name,
                'customer_email': customer.email,
                'customer_nif': getattr(customer, 'nif', None),
            }
            db.flush()
        return self.get_active_draft(db, admin_user_id)

    def add_line(self, db: Session, *, admin_user_id: int, ref: str, color: str | None, size: str | None, quantity: int) -> DraftData:
        with db.begin():
            product_ref = normalize_reference(ref)
            if not product_ref:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='ref_required')
            product = db.scalar(select(Product).options(selectinload(Product.category)).where(Product.ref == product_ref))
            if product is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='product_not_found')
            if not product.active or not product.manual_active or (product.category is not None and not product.category.active):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='product_not_available')
            product_colors = split_csv_values(product.colors_json or [])
            product_sizes = split_csv_values(product.sizes_json or [])
            color_value = normalize_text(color)
            size_value = normalize_text(size)
            if product_colors and color_value not in product_colors:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_color')
            if product_sizes and size_value not in product_sizes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_size')
            step = normalize_qty_step(product.quantity_step, default=1)
            qty = int(quantity or 0)
            if qty <= 0 or qty % step != 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity_step')
            unit_price = _unit_price(product.price)
            line_total = _money(unit_price * Decimal(qty))
            snapshot = {
                'product_ref': product.ref,
                'product_name': product.name,
                'product_type': product.product_type,
                'category_slug': product.category_slug,
                'catalog_slug': product.catalog_slug,
                'category_label': product.category.label if product.category else '',
                'color': color_value,
                'size': size_value,
                'quantity': qty,
                'quantity_step': step,
                'unit_price': f'{unit_price:.3f}' if product.catalog_slug == 'interpilhas' else f'{unit_price:.2f}',
                'line_total': f'{line_total:.2f}',
                'image_path': product.image_path,
                'image_checksum': product.image_checksum,
                'image_mime_type': product.image_mime_type,
            }
            draft = self._ensure_draft(db, admin_user_id)
            existing = db.scalar(
                select(AdminOrderDraftLine).where(
                    AdminOrderDraftLine.draft_id == draft.id,
                    AdminOrderDraftLine.product_ref == product.ref,
                    AdminOrderDraftLine.color == color_value,
                    AdminOrderDraftLine.size == size_value,
                ).with_for_update()
            )
            if existing is None:
                db.add(
                    AdminOrderDraftLine(
                        draft_id=draft.id,
                        product_ref=product.ref,
                        color=color_value,
                        size=size_value,
                        quantity=qty,
                        line_snapshot_json=snapshot,
                    )
                )
            else:
                existing.quantity = int(existing.quantity or 0) + qty
                existing.line_snapshot_json = snapshot
            draft.draft_snapshot_json = {**dict(draft.draft_snapshot_json or {}), 'updated_at': utcnow().isoformat()}
            db.flush()
        return self.get_active_draft(db, admin_user_id)

    def remove_line(self, db: Session, *, admin_user_id: int, line_id: int) -> DraftData:
        with db.begin():
            draft = self._ensure_draft(db, admin_user_id)
            line = db.scalar(select(AdminOrderDraftLine).where(AdminOrderDraftLine.id == line_id, AdminOrderDraftLine.draft_id == draft.id).with_for_update())
            if line is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='draft_line_not_found')
            db.delete(line)
            db.flush()
        return self.get_active_draft(db, admin_user_id)

    def clear(self, db: Session, *, admin_user_id: int) -> DraftData:
        with db.begin():
            draft = self._ensure_draft(db, admin_user_id)
            for line in list(draft.lines):
                db.delete(line)
            draft.customer_user_id = None
            draft.notes = None
            draft.pdf_notes = None
            draft.include_pdf_notes = False
            draft.draft_snapshot_json = {}
            db.flush()
        return self.get_active_draft(db, admin_user_id)

    def set_notes(self, db: Session, *, admin_user_id: int, notes: str | None, pdf_notes: str | None = None, include_pdf_notes: bool = False) -> DraftData:
        with db.begin():
            draft = self._ensure_draft(db, admin_user_id)
            draft.notes = normalize_text(notes) or None
            draft.pdf_notes = normalize_text(pdf_notes) or None
            draft.include_pdf_notes = bool(include_pdf_notes and draft.pdf_notes)
            db.flush()
        return self.get_active_draft(db, admin_user_id)

    def submit(self, db: Session, *, admin_user_id: int, request_id: str | None = None) -> dict[str, Any]:
        draft = self.get_active_draft(db, admin_user_id)
        if draft.customer_user_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='customer_required')
        if not draft.lines:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='draft_empty')
        db.rollback()
        order_service = OrderService()
        payload_lines = [
            {
                'ref': line.product_ref,
                'color': line.color,
                'size': line.size,
                'quantity': line.quantity,
            }
            for line in draft.lines
        ]
        order = order_service.create_order_from_lines(
            db,
            customer_user_id=draft.customer_user_id,
            actor_user_id=admin_user_id,
            origin='admin',
            idempotency_key=draft.request_id,
            request_id=request_id,
            notes=draft.notes,
            pdf_notes=draft.pdf_notes,
            include_pdf_notes=draft.include_pdf_notes,
            lines=payload_lines,
        )
        with db.begin():
            draft = db.get(AdminOrderDraft, draft.draft_id)
            if draft is not None:
                draft.is_active = False
        return order


class ExcelExportService:
    def _sheet_xml(self, rows: list[list[Any]]) -> str:
        xml_rows: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cells: list[str] = []
            for col_index, value in enumerate(row, start=1):
                ref = self._cell_ref(row_index, col_index)
                if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    text = _safe_excel_text(value)
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(text)}</t></is></c>')
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    def _cell_ref(self, row: int, col: int) -> str:
        letters = ''
        n = col
        while n:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return f'{letters}{row}'

    def build_workbook(self, summary_rows: list[list[Any]], order_rows: list[list[Any]]) -> bytes:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', self._content_types())
            zf.writestr('_rels/.rels', self._rels_root())
            zf.writestr('xl/workbook.xml', self._workbook())
            zf.writestr('xl/_rels/workbook.xml.rels', self._workbook_rels())
            zf.writestr('xl/styles.xml', self._styles())
            zf.writestr('xl/worksheets/sheet1.xml', self._sheet_xml(summary_rows))
            zf.writestr('xl/worksheets/sheet2.xml', self._sheet_xml(order_rows))
        return buffer.getvalue()

    def _content_types(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

    def _rels_root(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

    def _workbook(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets>'
            '<sheet name="Resumo" sheetId="1" r:id="rId1"/>'
            '<sheet name="Encomendas" sheetId="2" r:id="rId2"/>'
            '</sheets>'
            '</workbook>'
        )

    def _workbook_rels(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )

    def _styles(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '</styleSheet>'
        )

    def build_stats_export(self, *, report: MonthlyReportRow | AnnualReportRow, orders: Iterable[dict[str, Any]]) -> bytes:
        report_month = getattr(report, 'month', None)
        summary_rows = [
            ['Período', f'{report.year:04d}-{report_month:02d}' if report_month else f'{report.year:04d}'],
            ['Encomendas pendentes', report.pending_orders],
            ['Encomendas confirmadas', report.confirmed_orders],
            ['Encomendas enviadas', report.shipped_orders],
            ['Faturação confirmada', f'{report.confirmed_revenue:.2f}'],
            ['Unidades confirmadas', report.confirmed_units],
        ]
        order_rows = [
            ['Encomenda', 'Data', 'Data de confirmação', 'Cliente', 'Empresa', 'NIF', 'Catálogo', 'Estado', 'Unidades', 'Subtotal', 'Total', 'Origem', 'Criada por'],
        ]
        for order in orders:
            order_rows.append(
                [
                    _safe_excel_text(order.get('publicNumber')),
                    _safe_excel_text(order.get('createdAt')),
                    _safe_excel_text(order.get('confirmedAt')),
                    _safe_excel_text(order.get('customerName')),
                    _safe_excel_text(order.get('customerCompany')),
                    _safe_excel_text(order.get('customerNif')),
                    _safe_excel_text(order.get('catalogLabel')),
                    _safe_excel_text(order.get('orderStatusLabel')),
                    int(order.get('units') or 0),
                    _safe_excel_text(order.get('subtotal')),
                    _safe_excel_text(order.get('total')),
                    _safe_excel_text(order.get('origin')),
                    _safe_excel_text(order.get('createdByUsername')),
                ]
            )
        return self.build_workbook(summary_rows, order_rows)
