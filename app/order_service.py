from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .catalog import normalize_choice_text, normalize_qty_step, normalize_reference, normalize_text, split_csv_values, to_decimal
from .cart_catalog import cart_item_catalog, catalog_revision, increment_catalog_revision, minimum_total_for_catalog, normalize_cart_catalog
from .email_service import EmailService
from .gift_promotions import qualifying_gifts
from .models import Cart, CartItem, Catalog, EmailDeliveryLog, GiftPromotionRedemption, Order, OrderLine, OrderRequestId, OrderStatus, OrderStatusHistory, Product, User
from .promotions import active_promotions
from .security import public_order_number, utcnow


MONEY = Decimal('0.01')
UNIT_PRICE = Decimal('0.001')
def _money(value: Any) -> Decimal:
    return to_decimal(value, Decimal('0.00')).quantize(MONEY, rounding=ROUND_HALF_UP)


def _unit_price(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(UNIT_PRICE, rounding=ROUND_HALF_UP)


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def _order_identifier(order: Order) -> str:
    if order.public_number:
        return order.public_number
    return public_order_number((order.created_at or utcnow()).year, int(order.id or 0))


def _next_public_order_number(db: Session, year: int, preferred_sequence: int) -> str:
    sequence = max(1, int(preferred_sequence or 1))
    while True:
        public_number = public_order_number(year, sequence)
        if db.scalar(select(Order.id).where(Order.public_number == public_number)) is None:
            return public_number
        sequence += 1


def _status_label(status_value: str) -> str:
    mapping = {
        OrderStatus.PENDING.value: 'Pendente',
        OrderStatus.CONFIRMED.value: 'Confirmada',
        OrderStatus.SHIPPED.value: 'Enviada',
    }
    return mapping.get(status_value, status_value)


def _customer_snapshot(user: User) -> dict[str, Any]:
    metadata = dict(user.metadata_json or {})
    same_as_billing = bool(metadata.get('delivery_same_as_billing', not user.delivery_address_line1))
    return {
        'id': user.id,
        'username': normalize_text(user.username),
        'name': normalize_text(user.full_name),
        'company': normalize_text(user.company_name),
        'email': normalize_text(user.email),
        'emails': [normalize_text(user.email), *[normalize_text(value) for value in metadata.get('additional_emails') or []]],
        'phone': normalize_text(user.phone),
        'nif': normalize_text(getattr(user, 'nif', None)),
        'address_line1': normalize_text(user.address_line1),
        'address_line2': normalize_text(user.address_line2),
        'postal_code': normalize_text(user.postal_code),
        'city': normalize_text(user.city),
        'country': normalize_text(user.country),
        'billing_address_line1': normalize_text(user.address_line1),
        'billing_address_line2': normalize_text(user.address_line2),
        'billing_postal_code': normalize_text(user.postal_code),
        'billing_city': normalize_text(user.city),
        'billing_country': normalize_text(user.country),
        'delivery_same_as_billing': same_as_billing,
        'delivery_address_line1': normalize_text(user.address_line1 if same_as_billing else user.delivery_address_line1),
        'delivery_address_line2': normalize_text(user.address_line2 if same_as_billing else user.delivery_address_line2),
        'delivery_postal_code': normalize_text(user.postal_code if same_as_billing else user.delivery_postal_code),
        'delivery_city': normalize_text(user.city if same_as_billing else user.delivery_city),
        'delivery_country': normalize_text(user.country if same_as_billing else user.delivery_country),
        'carrier': normalize_text(metadata.get('carrier')),
        'metadata': metadata,
    }


def _product_available(product: Product) -> bool:
    return bool(product and product.active and product.manual_active and not product.gift_only and (product.category is None or product.category.active))


@dataclass(slots=True)
class HydratedOrderLine:
    product: Product
    color: str
    size: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    snapshot_json: dict[str, Any]
    gift_promotion_id: int | None = None


class OrderService:
    allowed_transitions = {
        OrderStatus.PENDING.value: {OrderStatus.CONFIRMED.value},
        OrderStatus.CONFIRMED.value: {OrderStatus.SHIPPED.value},
        OrderStatus.SHIPPED.value: set(),
    }

    def _lock_user(self, db: Session, user_id: int) -> User:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
        return user

    def _lock_cart(self, db: Session, user_id: int) -> Cart:
        cart = db.scalar(
            select(Cart)
            .options(selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.category))
            .where(Cart.user_id == user_id)
            .with_for_update()
        )
        if cart is None:
            cart = Cart(user_id=user_id, revision=0, catalog_revisions_json={}, source_version='v2')
            db.add(cart)
            db.flush()
        return cart

    def _request_payload_hash(
        self,
        *,
        customer_user_id: int,
        actor_user_id: int,
        origin: str,
        cart_revision: int | None,
        catalog_slug: str,
        items: Iterable[dict[str, Any]],
        notes: str | None,
        pdf_notes: str | None = None,
        include_pdf_notes: bool = False,
        ignore_quantity_step: bool = False,
        ignore_minimum_total: bool = False,
    ) -> str:
        payload = {
            'customer_user_id': customer_user_id,
            'actor_user_id': actor_user_id,
            'origin': normalize_text(origin).casefold(),
            'cart_revision': cart_revision,
            'catalog_slug': catalog_slug,
            'notes': normalize_text(notes),
            'pdf_notes': normalize_text(pdf_notes),
            'include_pdf_notes': bool(include_pdf_notes),
            'ignore_quantity_step': bool(ignore_quantity_step),
            'ignore_minimum_total': bool(ignore_minimum_total),
            'items': [
                {
                    'ref': normalize_reference(item.get('ref')),
                    'color': normalize_text(item.get('color')),
                    'size': normalize_text(item.get('size')),
                    'quantity': int(item.get('quantity') or 0),
                }
                for item in items
            ],
        }
        return _canonical_hash(payload)

    def _hydrate_lines(self, db: Session, items: Iterable[dict[str, Any]], *, customer_user_id: int | None = None, ignore_quantity_step: bool = False) -> list[HydratedOrderLine]:
        hydrated: list[HydratedOrderLine] = []
        for raw_item in items:
            ref = normalize_reference(raw_item.get('ref'))
            if not ref:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='product_not_found')
            product = db.scalar(select(Product).options(selectinload(Product.category)).where(Product.ref == ref))
            if product is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='product_not_found')
            if not _product_available(product):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='product_not_available')
            product_colors = split_csv_values(product.colors_json or [])
            product_sizes = split_csv_values(product.sizes_json or [])
            color_value = normalize_text(raw_item.get('color'))
            size_value = normalize_text(raw_item.get('size'))
            if product_colors and color_value not in product_colors:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_color')
            if product_sizes and size_value not in product_sizes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_size')
            original_step = normalize_qty_step(product.quantity_step, default=1)
            step = 1 if ignore_quantity_step else original_step
            quantity = int(raw_item.get('quantity') or 0)
            if quantity <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity')
            if quantity % step != 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity_step')
            promotion = active_promotions(db, customer_user_id, [product]).get(product.ref) if customer_user_id is not None else None
            unit_price = _unit_price(promotion.price if promotion else product.price)
            line_total = _money(unit_price * Decimal(quantity))
            snapshot = {
                'product_ref': product.ref,
                'product_name': normalize_text(product.name),
                'product_type': normalize_text(product.product_type),
                'category_slug': product.category_slug,
                'catalog_slug': product.catalog_slug,
                'category_label': normalize_text(product.category.label) if product.category else '',
                'category_sort_order': int(product.category.sort_order) if product.category else 9999,
                'product_sort_order': int(product.sort_order or 0),
                'color': color_value,
                'size': size_value,
                'quantity': quantity,
                'quantity_step': step,
                'original_quantity_step': original_step,
                'unit_price': f'{unit_price:.3f}' if product.catalog_slug == 'interpilhas' else f'{unit_price:.2f}',
                'original_price': f'{product.price:.3f}' if promotion else None,
                'campaign_id': promotion.campaign_id if promotion else None,
                'campaign_title': promotion.campaign_title if promotion else None,
                'line_total': f'{line_total:.2f}',
                'image_path': product.image_path,
                'image_checksum': product.image_checksum,
                'image_mime_type': product.image_mime_type,
            }
            hydrated.append(
                HydratedOrderLine(
                    product=product,
                    color=snapshot['color'],
                    size=snapshot['size'],
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                    snapshot_json=snapshot,
                )
            )
        return hydrated

    def _hydrate_cart_lines(self, cart: Cart) -> list[HydratedOrderLine]:
        if not cart.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='cart_empty')
        return self._hydrate_lines(
            db,
            (
                {
                    'ref': item.product_ref,
                    'color': item.color,
                    'size': item.size,
                    'quantity': item.quantity,
                }
                for item in sorted(cart.items, key=lambda row: (int(row.id or 0), row.product_ref, row.color, row.size))
            ),
        )

    def _cart_summary(self, lines: list[HydratedOrderLine]) -> dict[str, Any]:
        subtotal = sum((line.line_total for line in lines), Decimal('0.00')).quantize(MONEY, rounding=ROUND_HALF_UP)
        units = sum(line.quantity for line in lines)
        return {
            'subtotal': subtotal,
            'total': subtotal,
            'units': units,
            'lines': len(lines),
        }

    def _serialize_order_line(self, line: OrderLine) -> dict[str, Any]:
        snapshot = dict(line.snapshot_json or {})
        product = line.product
        category = product.category if product is not None else None
        catalog_slug = snapshot.get('catalog_slug') or (product.catalog_slug if product else 'villas')
        return {
            'id': line.id,
            'ref': line.product_ref,
            'name': line.product_name,
            'type': line.product_type,
            'color': normalize_choice_text(line.color),
            'size': normalize_choice_text(line.size),
            'quantity': int(line.quantity),
            'unitPrice': f'{_unit_price(line.unit_price):.3f}' if catalog_slug == 'interpilhas' else f'{_unit_price(line.unit_price):.2f}',
            'lineTotal': f'{_money(line.line_total):.2f}',
            'categorySlug': snapshot.get('category_slug') or (product.category_slug if product else None),
            'categoryLabel': snapshot.get('category_label') or (category.label if category else ''),
            'categorySortOrder': snapshot.get('category_sort_order', category.sort_order if category else 9999),
            'productSortOrder': snapshot.get('product_sort_order', product.sort_order if product else 9999),
            'catalogSlug': catalog_slug,
            'snapshot': snapshot,
        }

    def _serialize_order(self, order: Order, *, include_lines: bool = True, include_internal: bool = False) -> dict[str, Any]:
        lines = list(order.items or [])
        line_items = [self._serialize_order_line(line) for line in lines] if include_lines else []
        order_snapshot = dict(order.snapshot_json or {})
        catalog_slug = order_snapshot.get('catalog_slug') or (self._serialize_order_line(lines[0])['catalogSlug'] if lines else 'villas')
        catalog_label = order_snapshot.get('catalog_label') or ('Utilidades' if catalog_slug == 'interpilhas' else 'Villas' if catalog_slug == 'villas' else str(catalog_slug).replace('-', ' ').title())
        public_number = _order_identifier(order)
        customer_snapshot = dict(order.customer_snapshot_json or {})
        customer_metadata = dict(customer_snapshot.get('metadata') or {})
        current_metadata = dict(order.user.metadata_json or {}) if order.user is not None else {}
        current_emails = EmailService.user_recipients(order.user) if order.user is not None else []
        return {
            'id': order.id,
            'publicNumber': public_number,
            'requestId': order.request_id,
            'userId': order.user_id,
            'customerName': order.customer_name,
            'customerNif': order.customer_nif or '',
            'customerEmail': order.customer_email or '',
            'customerEmails': list(dict.fromkeys([value for value in [order.customer_email, *customer_snapshot.get('emails', []), *current_emails] if value])),
            'customerPhone': order.customer_phone or '',
            'customerCompany': order.customer_company or '',
            'customerAddressLine1': order.customer_address_line1 or '',
            'customerAddressLine2': order.customer_address_line2 or '',
            'customerPostalCode': order.customer_postal_code or '',
            'customerCity': order.customer_city or '',
            'customerCountry': order.customer_country or '',
            'customerCarrier': customer_snapshot.get('carrier') or customer_metadata.get('carrier') or current_metadata.get('carrier') or '',
            'customerBillingAddressLine1': customer_snapshot.get('billing_address_line1') or order.customer_address_line1 or '',
            'customerBillingAddressLine2': customer_snapshot.get('billing_address_line2') or order.customer_address_line2 or '',
            'customerBillingPostalCode': customer_snapshot.get('billing_postal_code') or order.customer_postal_code or '',
            'customerBillingCity': customer_snapshot.get('billing_city') or order.customer_city or '',
            'customerBillingCountry': customer_snapshot.get('billing_country') or order.customer_country or '',
            'customerDeliveryAddressLine1': customer_snapshot.get('delivery_address_line1') or order.customer_address_line1 or '',
            'customerDeliveryAddressLine2': customer_snapshot.get('delivery_address_line2') or order.customer_address_line2 or '',
            'customerDeliveryPostalCode': customer_snapshot.get('delivery_postal_code') or order.customer_postal_code or '',
            'customerDeliveryCity': customer_snapshot.get('delivery_city') or order.customer_city or '',
            'customerDeliveryCountry': customer_snapshot.get('delivery_country') or order.customer_country or '',
            'createdByUserId': order.created_by_user_id,
            'createdByUsername': order.created_by_user.username if order.created_by_user else '',
            'origin': order.origin or 'client',
            'catalogSlug': catalog_slug,
            'catalogLabel': catalog_label,
            'confirmedAt': order.confirmed_at,
            'subtotal': f'{_money(order.subtotal):.2f}',
            'total': f'{_money(order.total):.2f}',
            'units': int(order.units),
            'lines': int(order.lines),
            'notes': order.notes or '' if include_internal else '',
            'internalNotes': order.notes or '' if include_internal else '',
            'pdfNotes': order.pdf_notes or '' if include_internal or order.include_pdf_notes else '',
            'includePdfNotes': bool(order.include_pdf_notes),
            'orderStatus': order.order_status,
            'orderStatusLabel': _status_label(order.order_status),
            'emailStatus': order.email_status,
            'emailError': order.email_error or '',
            'emailSentAt': order.email_sent_at,
            'createdAt': order.created_at,
            'updatedAt': order.updated_at,
            'customerSnapshot': customer_snapshot,
            'snapshot': order_snapshot,
            'items': line_items,
            'pdfUrl': f'/api/v1/orders/{public_number}/pdf',
            'pdfNoPricesUrl': f'/api/v1/orders/{public_number}/pdf?hide_prices=1',
            'url': f'/me/encomendas/{public_number}',
        }

    def _order_query(self):
        return (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderLine.product).selectinload(Product.category),
                selectinload(Order.history),
                selectinload(Order.user),
                selectinload(Order.created_by_user),
            )
        )

    def _load_order(self, db: Session, identifier: str | int, *, user_id: int | None = None) -> Order | None:
        stmt = self._order_query()
        if isinstance(identifier, int) or str(identifier).isdigit():
            stmt = stmt.where(Order.id == int(identifier))
        else:
            stmt = stmt.where(Order.public_number == str(identifier))
        if user_id is not None:
            stmt = stmt.where(Order.user_id == user_id)
        return db.scalar(stmt)

    def _create_order_from_lines(
        self,
        db: Session,
        *,
        customer_user_id: int,
        actor_user_id: int,
        idempotency_key: str,
        request_id: str | None,
        origin: str,
        lines: Iterable[dict[str, Any]] | None = None,
        source_cart_user_id: int | None = None,
        notes: str | None = None,
        pdf_notes: str | None = None,
        include_pdf_notes: bool = False,
        cart_revision: int | None = None,
        clear_cart: bool = False,
        catalog_slug: str | None = None,
        ignore_quantity_step: bool = False,
        ignore_minimum_total: bool = False,
    ) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='idempotency_key_required')
        request_id_value = normalize_text(idempotency_key)
        http_request_id = normalize_text(request_id) or None
        with db.begin():
            customer = self._lock_user(db, customer_user_id)
            actor = self._lock_user(db, actor_user_id)
            existing_request = db.get(OrderRequestId, request_id_value)
            if existing_request is not None:
                existing_order = self._load_order(db, existing_request.order_id, user_id=customer.id if normalize_text(origin).casefold() == 'client' else None)
                if existing_order is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')
                return self._serialize_order(existing_order, include_internal=normalize_text(origin).casefold() != 'client')

            cart = None
            requested_catalog = normalize_cart_catalog(catalog_slug) if catalog_slug else None
            if normalize_text(origin).casefold() in {'client', 'admin_cart'}:
                requested_catalog = requested_catalog or 'villas'
                cart = self._lock_cart(db, source_cart_user_id or customer.id)
                if cart_revision is not None and catalog_revision(cart, requested_catalog) != int(cart_revision):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='cart_revision_mismatch')
                if lines is None:
                    lines = [
                        {
                            'ref': item.product_ref,
                            'color': item.color,
                            'size': item.size,
                            'quantity': item.quantity,
                        }
                        for item in sorted(cart.items, key=lambda row: (int(row.id or 0), row.product_ref, row.color, row.size))
                        if cart_item_catalog(item) == requested_catalog
                    ]
            if lines is None:
                lines = []

            allow_non_multiple = bool(ignore_quantity_step and normalize_text(actor.role).casefold() in {'admin', 'developer'})
            allow_below_minimum = bool(ignore_minimum_total and normalize_text(actor.role).casefold() in {'admin', 'developer'})
            hydrated_lines = self._hydrate_lines(db, lines, customer_user_id=customer.id, ignore_quantity_step=allow_non_multiple)
            line_catalogs = {normalize_cart_catalog(line.product.catalog_slug) for line in hydrated_lines}
            if len(line_catalogs) > 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='mixed_catalog_order')
            actual_catalog = requested_catalog or (next(iter(line_catalogs)) if line_catalogs else 'villas')
            if line_catalogs and actual_catalog not in line_catalogs:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='product_catalog_mismatch')
            gift_awards = qualifying_gifts(
                db,
                user_id=customer.id,
                catalog_slug=actual_catalog,
                lines=[
                    {'ref': line.product.ref, 'quantity': line.quantity, 'line_total': line.line_total}
                    for line in hydrated_lines
                ],
            )
            for award in gift_awards:
                gift = award.product
                quantity = award.quantity
                hydrated_lines.append(HydratedOrderLine(
                    product=gift,
                    color='',
                    size='',
                    quantity=quantity,
                    unit_price=Decimal('0.000'),
                    line_total=Decimal('0.00'),
                    gift_promotion_id=award.promotion.id,
                    snapshot_json={
                        'product_ref': gift.ref,
                        'product_name': normalize_text(gift.name),
                        'product_type': normalize_text(gift.product_type),
                        'category_slug': gift.category_slug,
                        'catalog_slug': gift.catalog_slug,
                        'category_label': normalize_text(gift.category.label) if gift.category else '',
                        'category_sort_order': int(gift.category.sort_order) if gift.category else 9999,
                        'product_sort_order': int(gift.sort_order or 0),
                        'color': '',
                        'size': '',
                        'quantity': quantity,
                        'quantity_step': 1,
                        'original_quantity_step': int(gift.quantity_step or 1),
                        'unit_price': '0.00',
                        'original_price': None,
                        'campaign_id': None,
                        'campaign_title': None,
                        'line_total': '0.00',
                        'image_path': gift.image_path,
                        'image_checksum': gift.image_checksum,
                        'image_mime_type': gift.image_mime_type,
                        'is_gift': True,
                        'gift_promotion_id': award.promotion.id,
                        'gift_promotion_title': award.promotion.title,
                    },
                ))
            summary = self._cart_summary(hydrated_lines)
            if summary['lines'] == 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='cart_empty')
            if not allow_below_minimum and normalize_text(origin).casefold() in {'client', 'admin_cart'} and summary['total'] < minimum_total_for_catalog(actual_catalog, db):
                detail = 'minimum_order_total_interpilhas' if actual_catalog == 'interpilhas' else 'minimum_order_total'
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

            customer_snapshot = _customer_snapshot(customer)
            request_hash = self._request_payload_hash(
                customer_user_id=customer.id,
                actor_user_id=actor.id,
                origin=origin,
                cart_revision=cart_revision,
                catalog_slug=actual_catalog,
                items=[line.snapshot_json for line in hydrated_lines],
                notes=notes,
                pdf_notes=pdf_notes,
                include_pdf_notes=include_pdf_notes,
                ignore_quantity_step=allow_non_multiple,
                ignore_minimum_total=allow_below_minimum,
            )
            origin_value = normalize_text(origin).casefold() or 'client'
            created_by_admin = normalize_text(actor.role).casefold() in {'admin', 'developer'}
            initial_status = OrderStatus.CONFIRMED.value if created_by_admin else OrderStatus.PENDING.value
            confirmed_at = utcnow() if initial_status == OrderStatus.CONFIRMED.value else None
            order = Order(
                public_number=f'TMP-{request_id_value[:20]}',
                request_id=request_id_value,
                user_id=customer.id,
                created_by_user_id=actor.id,
                origin=origin_value,
                customer_name=customer_snapshot['name'] or customer.full_name,
                customer_nif=customer_snapshot['nif'] or None,
                customer_email=customer_snapshot['email'] or None,
                customer_phone=customer_snapshot['phone'] or None,
                customer_company=customer_snapshot['company'] or None,
                customer_address_line1=customer_snapshot['delivery_address_line1'] or None,
                customer_address_line2=customer_snapshot['delivery_address_line2'] or None,
                customer_postal_code=customer_snapshot['delivery_postal_code'] or None,
                customer_city=customer_snapshot['delivery_city'] or None,
                customer_country=customer_snapshot['delivery_country'] or None,
                subtotal=summary['subtotal'],
                total=summary['total'],
                units=summary['units'],
                lines=summary['lines'],
                notes=normalize_text(notes) or None,
                pdf_notes=normalize_text(pdf_notes) or None,
                include_pdf_notes=bool(include_pdf_notes and normalize_text(pdf_notes)),
                order_status=initial_status,
                confirmed_at=confirmed_at,
                email_status='pending',
                customer_snapshot_json=customer_snapshot,
                snapshot_json={
                    'request_id': request_id_value,
                    'http_request_id': http_request_id,
                    'cart_revision': cart_revision,
                    'catalog_slug': actual_catalog,
                    'catalog_label': (db.get(Catalog, actual_catalog).label if db.get(Catalog, actual_catalog) else actual_catalog.replace('-', ' ').title()),
                    'customer': customer_snapshot,
                    'actor': {'id': actor.id, 'username': actor.username, 'role': actor.role},
                    'origin': origin_value,
                    'ignored_quantity_step': allow_non_multiple,
                    'ignored_minimum_total': allow_below_minimum,
                    'summary': {
                        'subtotal': f"{summary['subtotal']:.2f}",
                        'total': f"{summary['total']:.2f}",
                        'units': summary['units'],
                        'lines': summary['lines'],
                    },
                },
            )
            db.add(order)
            db.flush()
            order.public_number = _next_public_order_number(db, (order.created_at or utcnow()).year, order.id)

            db.add(
                OrderRequestId(
                    request_id=request_id_value,
                    order_id=order.id,
                    request_hash=request_hash,
                )
            )

            for line in hydrated_lines:
                order.items.append(
                    OrderLine(
                        product_ref=line.product.ref,
                        product_name=line.snapshot_json['product_name'],
                        product_type=line.snapshot_json['product_type'],
                        color=line.color,
                        size=line.size,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        line_total=line.line_total,
                        snapshot_json=line.snapshot_json,
                    )
                )

            for award in gift_awards:
                db.add(GiftPromotionRedemption(
                    promotion_id=award.promotion.id,
                    user_id=customer.id,
                    order_id=order.id,
                ))

            db.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=None,
                    new_status=initial_status,
                    changed_by_user_id=actor.id,
                    request_id=http_request_id,
                    note='order_created_by_admin' if created_by_admin else 'order_created',
                    changed_at=confirmed_at or utcnow(),
                )
            )

            if cart is not None and clear_cart:
                for item in list(cart.items):
                    if cart_item_catalog(item) == actual_catalog:
                        db.delete(item)
                increment_catalog_revision(cart, actual_catalog)

            db.flush()
            order_dict = self._serialize_order(order, include_internal=True)
        return order_dict

    def submit_order(
        self,
        db: Session,
        *,
        user_id: int,
        customer_user_id: int | None = None,
        idempotency_key: str,
        request_id: str | None,
        cart_revision: int | None,
        notes: str | None = None,
        pdf_notes: str | None = None,
        include_pdf_notes: bool = False,
        catalog_slug: str = 'villas',
        ignore_quantity_step: bool = False,
        ignore_minimum_total: bool = False,
    ) -> dict[str, Any]:
        customer_id = customer_user_id or user_id
        try:
            order = self.create_order_from_lines(
                db,
                customer_user_id=customer_id,
                actor_user_id=user_id,
                origin='admin_cart' if customer_id != user_id else 'client',
                idempotency_key=idempotency_key,
                request_id=request_id,
                cart_revision=cart_revision,
                notes=notes,
                pdf_notes=pdf_notes,
                include_pdf_notes=include_pdf_notes,
                lines=None,
                source_cart_user_id=user_id,
                clear_cart=True,
                catalog_slug=catalog_slug,
                ignore_quantity_step=ignore_quantity_step,
                ignore_minimum_total=ignore_minimum_total,
            )
            return order
        except IntegrityError:
            db.rollback()
            existing_request = db.get(OrderRequestId, normalize_text(idempotency_key))
            if existing_request is None:
                raise
            existing_order = self._load_order(db, existing_request.order_id, user_id=customer_id)
            if existing_order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')
            return self._serialize_order(existing_order, include_internal=customer_id != user_id)

    def create_order_from_lines(
        self,
        db: Session,
        *,
        customer_user_id: int,
        actor_user_id: int,
        origin: str,
        idempotency_key: str,
        request_id: str | None,
        lines: Iterable[dict[str, Any]] | None = None,
        notes: str | None = None,
        pdf_notes: str | None = None,
        include_pdf_notes: bool = False,
        cart_revision: int | None = None,
        clear_cart: bool = False,
        source_cart_user_id: int | None = None,
        catalog_slug: str | None = None,
        ignore_quantity_step: bool = False,
        ignore_minimum_total: bool = False,
    ) -> dict[str, Any]:
        try:
            return self._create_order_from_lines(
                db,
                customer_user_id=customer_user_id,
                actor_user_id=actor_user_id,
                idempotency_key=idempotency_key,
                request_id=request_id,
                origin=origin,
                lines=lines,
                notes=notes,
                pdf_notes=pdf_notes,
                include_pdf_notes=include_pdf_notes,
                cart_revision=cart_revision,
                clear_cart=clear_cart,
                source_cart_user_id=source_cart_user_id,
                catalog_slug=catalog_slug,
                ignore_quantity_step=ignore_quantity_step,
                ignore_minimum_total=ignore_minimum_total,
            )
        except IntegrityError:
            db.rollback()
            existing_request = db.get(OrderRequestId, normalize_text(idempotency_key))
            if existing_request is None:
                raise
            existing_order = self._load_order(db, existing_request.order_id, user_id=customer_user_id if normalize_text(origin).casefold() == 'client' else None)
            if existing_order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')
            return self._serialize_order(existing_order, include_internal=normalize_text(origin).casefold() != 'client')

    def list_client_orders(self, db: Session, *, user_id: int) -> list[dict[str, Any]]:
        stmt = self._order_query().where(Order.user_id == user_id).order_by(desc(Order.created_at), desc(Order.id))
        orders = list(db.execute(stmt).scalars().all())
        return [self._serialize_order(order, include_lines=False) for order in orders]

    def list_admin_orders(
        self,
        db: Session,
        *,
        q: str | None = None,
        status_filter: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        stmt = self._order_query()
        if q:
            pattern = f'%{q.strip()}%'
            stmt = stmt.outerjoin(Order.items).where(
                or_(
                    Order.public_number.like(pattern),
                    Order.customer_name.like(pattern),
                    Order.customer_company.like(pattern),
                    Order.customer_nif.like(pattern),
                    Order.customer_email.like(pattern),
                    OrderLine.product_ref.like(pattern),
                    OrderLine.product_name.like(pattern),
                )
            )
        if status_filter:
            stmt = stmt.where(Order.order_status == status_filter)
        if date_from:
            stmt = stmt.where(Order.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Order.created_at <= date_to)
        stmt = stmt.order_by(desc(Order.created_at), desc(Order.id)).limit(limit)
        orders = list(db.execute(stmt).scalars().unique().all())
        return [self._serialize_order(order, include_lines=False, include_internal=True) for order in orders]

    def get_order(self, db: Session, identifier: str | int, *, user_id: int | None = None, admin: bool = False) -> dict[str, Any] | None:
        order = self._load_order(db, identifier, user_id=None if admin else user_id)
        if order is None:
            return None
        return self._serialize_order(order, include_internal=admin)

    def status_history(self, db: Session, order_id: int) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(OrderStatusHistory)
                .where(OrderStatusHistory.order_id == order_id)
                .order_by(OrderStatusHistory.changed_at.asc(), OrderStatusHistory.id.asc())
            ).scalars().all()
        )
        return [
            {
                'id': row.id,
                'orderId': row.order_id,
                'oldStatus': row.old_status or '',
                'newStatus': row.new_status,
                'changedByUserId': row.changed_by_user_id,
                'requestId': row.request_id or '',
                'note': row.note or '',
                'changedAt': row.changed_at,
            }
            for row in rows
        ]

    def email_logs(self, db: Session, order_id: int) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(EmailDeliveryLog)
                .where(EmailDeliveryLog.related_order_id == order_id)
                .order_by(EmailDeliveryLog.created_at.asc(), EmailDeliveryLog.id.asc())
            ).scalars().all()
        )
        return [
            {
                'id': row.id,
                'requestId': row.request_id or '',
                'attempt': int(row.attempt or 1),
                'templateName': row.template_name or '',
                'recipient': row.recipient,
                'subject': row.subject,
                'status': row.status,
                'providerMessageId': row.provider_message_id or '',
                'errorMessage': row.error_message or '',
                'createdAt': row.created_at,
                'payload': dict(row.payload_json or {}),
            }
            for row in rows
        ]

    def update_internal_notes(
        self,
        db: Session,
        *,
        identifier: str | int,
        notes: str | None,
        changed_by_user_id: int,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        with db.begin():
            stmt = self._order_query().where(
                Order.id == int(identifier) if str(identifier).isdigit() else Order.public_number == str(identifier)
            ).with_for_update()
            order = db.scalar(stmt)
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')
            order.notes = normalize_text(notes) or None
            db.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=order.order_status,
                    new_status=order.order_status,
                    changed_by_user_id=changed_by_user_id,
                    request_id=normalize_text(request_id) or None,
                    note='internal_notes_updated',
                    changed_at=utcnow(),
                )
            )
            db.flush()
            return self._serialize_order(order, include_internal=True)

    def update_pdf_notes(
        self,
        db: Session,
        *,
        identifier: str | int,
        notes: str | None,
        include: bool,
        changed_by_user_id: int,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        with db.begin():
            stmt = self._order_query().where(
                Order.id == int(identifier) if str(identifier).isdigit() else Order.public_number == str(identifier)
            ).with_for_update()
            order = db.scalar(stmt)
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')
            order.pdf_notes = normalize_text(notes) or None
            order.include_pdf_notes = bool(include and order.pdf_notes)
            db.add(OrderStatusHistory(
                order_id=order.id,
                old_status=order.order_status,
                new_status=order.order_status,
                changed_by_user_id=changed_by_user_id,
                request_id=normalize_text(request_id) or None,
                note='pdf_notes_updated',
                changed_at=utcnow(),
            ))
            db.flush()
            return self._serialize_order(order, include_internal=True)

    def change_status(
        self,
        db: Session,
        *,
        identifier: str | int,
        new_status: str,
        changed_by_user_id: int,
        request_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        new_status = normalize_text(new_status).casefold()
        if new_status not in self.allowed_transitions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_order_status')

        with db.begin():
            stmt = self._order_query().where(
                Order.id == int(identifier) if str(identifier).isdigit() else Order.public_number == str(identifier)
            ).with_for_update()
            order = db.scalar(stmt)
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='order_not_found')

            current_status = normalize_text(order.order_status).casefold() or OrderStatus.PENDING.value
            if current_status == new_status:
                result = self._serialize_order(order, include_internal=True)
                result['statusChanged'] = False
                return result
            allowed = self.allowed_transitions.get(current_status, set())
            if new_status not in allowed:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='invalid_status_transition')

            order.order_status = new_status
            if new_status == OrderStatus.CONFIRMED.value and order.confirmed_at is None:
                order.confirmed_at = utcnow()
            db.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=current_status,
                    new_status=new_status,
                    changed_by_user_id=changed_by_user_id,
                    request_id=normalize_text(request_id) or None,
                    note=normalize_text(note) or None,
                    changed_at=utcnow(),
                )
            )
            db.flush()
            result = self._serialize_order(order, include_internal=True)
            result['statusChanged'] = True
            return result
