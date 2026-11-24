from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .catalog import normalize_choice_text, normalize_qty_step, normalize_reference, normalize_text, split_csv_values, to_decimal
from .cart_catalog import cart_item_catalog, catalog_revision, increment_catalog_revision, minimum_total_for_catalog, normalize_cart_catalog
from .models import Cart, CartItem, CartOperation, Product, User
from .gift_promotions import qualifying_gifts
from .promotions import PromotionInfo, active_promotions

MONEY = Decimal('0.01')
UNIT_PRICE = Decimal('0.001')


def _money(value: Any) -> Decimal:
    return to_decimal(value, Decimal('0.00')).quantize(MONEY, rounding=ROUND_HALF_UP)


def _unit_price(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(UNIT_PRICE, rounding=ROUND_HALF_UP)


def _hash_payload(operation: str, payload: dict[str, Any]) -> str:
    normalized = {'operation': operation, 'payload': payload}
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def _variant_key(color: str | None, size: str | None) -> tuple[str, str]:
    return normalize_text(color), normalize_text(size)


@dataclass(slots=True)
class HydratedItem:
    product: Product
    color: str
    size: str
    quantity: int


class CartService:
    def _lock_user(self, db: Session, user_id: int) -> User:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user_not_found')
        return user

    def _lock_cart(self, db: Session, user_id: int) -> Cart:
        cart = db.scalar(select(Cart).where(Cart.user_id == user_id).with_for_update())
        if cart is None:
            cart = Cart(user_id=user_id, revision=0, catalog_revisions_json={}, source_version='v2')
            db.add(cart)
            db.flush()
        return cart

    def _operation_key(self, db: Session, user_id: int, idempotency_key: str) -> CartOperation | None:
        stmt = select(CartOperation).where(CartOperation.user_id == user_id, CartOperation.idempotency_key == idempotency_key).with_for_update()
        return db.scalar(stmt)

    def _cart_items_query(self, user_id: int):
        return (
            select(Cart)
            .options(selectinload(Cart.items).selectinload(CartItem.product))
            .where(Cart.user_id == user_id)
        )

    def _product_is_available(self, product: Product) -> bool:
        return bool(product.active and product.manual_active and not product.gift_only and (product.category is None or product.category.active))

    def _normalize_variant(self, raw_value: str | None, values: list[str], *, field_name: str) -> str:
        normalized = normalize_text(raw_value)
        if not values:
            return ''
        lookup = {normalize_text(value).casefold(): value for value in values}
        if not normalized:
            if len(values) == 1:
                return values[0]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{field_name}_required')
        resolved = lookup.get(normalized.casefold())
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'invalid_{field_name}')
        return resolved

    def _normalize_quantity(self, quantity: int | None, step: int) -> int:
        if quantity is None:
            return step
        try:
            normalized = int(quantity)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity')
        if normalized <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity')
        if normalized % step != 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_quantity_step')
        return normalized

    def _hydrate_product(self, db: Session, ref: str) -> Product:
        product = db.scalar(
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.ref == normalize_reference(ref))
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='product_not_found')
        if not self._product_is_available(product):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='product_not_available')
        return product

    def _cart_item_snapshot(self, db: Session, user_id: int, product: Product, color: str, size: str, quantity: int) -> dict[str, Any]:
        promotion = active_promotions(db, user_id, [product]).get(product.ref)
        unit_price = _unit_price(promotion.price if promotion else product.price)
        line_total = _money(unit_price * Decimal(quantity))
        return {
            'product_name_snapshot': normalize_text(product.name),
            'product_type_snapshot': normalize_text(product.product_type),
            'product_image_snapshot': product.image_path,
            'product_snapshot': {
                'ref': product.ref,
                'name': normalize_text(product.name),
                'product_type': normalize_text(product.product_type),
                'category_slug': product.category_slug,
                'catalog_slug': product.catalog_slug,
                'colors': list(product.colors_json or []),
                'sizes': list(product.sizes_json or []),
                'image_path': product.image_path,
                'image_checksum': product.image_checksum,
                'image_mime_type': product.image_mime_type,
                'quantity_step': int(product.quantity_step or 1),
                'quick_quantities': list((product.metadata_json or {}).get('quick_quantities') or []),
                'original_price': f'{product.price:.3f}',
                'campaign_id': promotion.campaign_id if promotion else None,
                'campaign_title': promotion.campaign_title if promotion else None,
            },
            'unit_price_snapshot': unit_price,
            'line_total_snapshot': line_total,
            'color': color,
            'size': size,
            'quantity': quantity,
        }

    def _serialize_item(self, item: CartItem, promotion: PromotionInfo | None = None) -> dict[str, Any]:
        product = item.product
        product_data = item.product_snapshot or {}
        available = bool(product and self._product_is_available(product))
        display_name = normalize_text(product.name) if product else normalize_text(item.product_name_snapshot)
        display_type = normalize_text(product.product_type) if product else normalize_text(item.product_type_snapshot)
        image_path = product.image_path if product and product.image_path else item.product_image_snapshot or product_data.get('image_path')
        quantity_step = int(product.quantity_step or 1) if product else int(product_data.get('quantity_step') or 1)
        catalog_slug = product.catalog_slug if product else product_data.get('catalog_slug', 'villas')
        configured_shortcuts = list((product.metadata_json or {}).get('quick_quantities') or []) if product else list(product_data.get('quick_quantities') or [])
        quick_quantities = sorted({int(value) for value in configured_shortcuts if str(value).isdigit() and int(value) >= quantity_step and int(value) % quantity_step == 0})
        if not quick_quantities and catalog_slug == 'interpilhas' and product is not None:
            quick_quantities = sorted({int(value) for value in (product.case_inner, product.case_outer) if value and int(value) >= quantity_step and int(value) % quantity_step == 0})
        price = _unit_price(promotion.price if promotion else (product.price if product else item.unit_price_snapshot))
        line_total = _money(price * Decimal(int(item.quantity)))
        return {
            'id': item.id,
            'ref': item.product_ref,
            'name': display_name,
            'type': display_type,
            'color': normalize_choice_text(item.color),
            'size': normalize_choice_text(item.size),
            'quantity': int(item.quantity),
            'quantity_step': quantity_step,
            'quick_quantities': quick_quantities[:4],
            'unit_price': f'{price:.3f}' if catalog_slug == 'interpilhas' else f'{price:.2f}',
            'line_total': f'{line_total:.2f}',
            'original_price': (f'{promotion.original_price:.3f}' if catalog_slug == 'interpilhas' else f'{promotion.original_price:.2f}') if promotion else None,
            'promotion': {'campaignId': promotion.campaign_id, 'title': promotion.campaign_title, 'label': promotion.label} if promotion else None,
            'catalog_slug': catalog_slug,
            'image_path': image_path,
            'available': available,
            'warning': None if available else 'Produto indisponível',
            'is_gift': False,
        }

    def _serialize_cart(self, cart: Cart | None, catalog_slug: str = 'villas', db: Session | None = None) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        if cart is None:
            return {
                'catalog_slug': catalog_slug,
                'minimum_total': f'{minimum_total_for_catalog(catalog_slug, db):.2f}',
                'revision': 0,
                'units': 0,
                'lines': 0,
                'subtotal': '0.00',
                'total': '0.00',
                'items': [],
                'updatedAt': None,
            }
        ordered_items = sorted(
            (item for item in cart.items if cart_item_catalog(item) == catalog_slug),
            key=lambda item: (int(item.id or 0), item.product_ref, item.color, item.size),
        )
        promotions = active_promotions(db, cart.user_id, [item.product for item in ordered_items if item.product]) if db is not None else {}
        items = [self._serialize_item(item, promotions.get(item.product_ref)) for item in ordered_items]
        if db is not None:
            awards = qualifying_gifts(
                db,
                user_id=cart.user_id,
                catalog_slug=catalog_slug,
                lines=[{'ref': item['ref'], 'quantity': item['quantity'], 'line_total': item['line_total']} for item in items],
            )
            for award in awards:
                gift = award.product
                quantity = award.quantity
                items.append({
                    'id': f'gift-{award.promotion.id}',
                    'ref': gift.ref,
                    'name': gift.name,
                    'type': gift.product_type,
                    'color': '',
                    'size': '',
                    'quantity': quantity,
                    'quantity_step': 1,
                    'quick_quantities': [],
                    'unit_price': '0.00',
                    'line_total': '0.00',
                    'original_price': None,
                    'promotion': {'giftPromotionId': award.promotion.id, 'title': award.promotion.title, 'label': 'Oferta automática'},
                    'catalog_slug': gift.catalog_slug,
                    'image_path': gift.image_path,
                    'available': True,
                    'warning': None,
                    'is_gift': True,
                })
        units = sum(int(item['quantity']) for item in items)
        subtotal = sum((Decimal(item['line_total']) for item in items), Decimal('0.00')).quantize(MONEY, rounding=ROUND_HALF_UP)
        return {
            'catalog_slug': catalog_slug,
            'minimum_total': f'{minimum_total_for_catalog(catalog_slug, db):.2f}',
            'revision': catalog_revision(cart, catalog_slug),
            'units': units,
            'lines': len(items),
            'subtotal': f'{subtotal:.2f}',
            'total': f'{subtotal:.2f}',
            'items': items,
        'updatedAt': cart.updated_at.isoformat() if cart.updated_at else None,
        }

    def get_cart(self, db: Session, user_id: int, catalog_slug: str = 'villas') -> dict[str, Any]:
        cart = db.scalar(self._cart_items_query(user_id))
        return self._serialize_cart(cart, catalog_slug, db)

    def _load_operation_response(self, operation: CartOperation) -> dict[str, Any]:
        return operation.response_json or {}

    def _store_operation(self, db: Session, *, user_id: int, key: str, operation: str, request_hash: str, cart_revision: int, response: dict[str, Any]) -> None:
        db.add(
            CartOperation(
                user_id=user_id,
                idempotency_key=key,
                operation=operation,
                request_hash=request_hash,
                cart_revision=cart_revision,
                response_json=response,
            )
        )

    def _ensure_revision(self, cart: Cart, expected_revision: int | None, catalog_slug: str = 'villas') -> None:
        if expected_revision is None:
            return
        if catalog_revision(cart, catalog_slug) != int(expected_revision):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='cart_revision_mismatch')

    def _add_or_update_item(self, db: Session, cart: Cart, product: Product, color: str, size: str, quantity: int) -> CartItem:
        existing = next((item for item in cart.items if item.product_ref == product.ref and item.color == color and item.size == size), None)
        if existing is None:
            snapshot = self._cart_item_snapshot(db, cart.user_id, product, color, size, quantity)
            item = CartItem(
                cart_user_id=cart.user_id,
                product_ref=product.ref,
                color=color,
                size=size,
                quantity=quantity,
                unit_price_snapshot=snapshot['unit_price_snapshot'],
                line_total_snapshot=snapshot['line_total_snapshot'],
                product_name_snapshot=snapshot['product_name_snapshot'],
                product_type_snapshot=snapshot['product_type_snapshot'],
                product_image_snapshot=snapshot['product_image_snapshot'],
                product_snapshot=snapshot['product_snapshot'],
            )
            cart.items.append(item)
            return item
        existing.quantity = int(existing.quantity) + quantity
        snapshot = self._cart_item_snapshot(db, cart.user_id, product, color, size, existing.quantity)
        existing.unit_price_snapshot = snapshot['unit_price_snapshot']
        existing.line_total_snapshot = snapshot['line_total_snapshot']
        existing.product_name_snapshot = snapshot['product_name_snapshot']
        existing.product_type_snapshot = snapshot['product_type_snapshot']
        existing.product_image_snapshot = snapshot['product_image_snapshot']
        existing.product_snapshot = snapshot['product_snapshot']
        return existing

    def add_item(
        self,
        db: Session,
        *,
        user_id: int,
        idempotency_key: str,
        ref: str,
        color: str | None = None,
        size: str | None = None,
        quantity: int | None = None,
        expected_revision: int | None = None,
        catalog_slug: str = 'villas',
    ) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        payload = {
            'catalog_slug': catalog_slug,
            'ref': normalize_reference(ref),
            'color': normalize_text(color),
            'size': normalize_text(size),
            'quantity': quantity,
            'expected_revision': expected_revision,
        }
        request_hash = _hash_payload('add_item', payload)

        try:
            with db.begin():
                self._lock_user(db, user_id)
                cart = self._lock_cart(db, user_id)
                existing_operation = self._operation_key(db, user_id, idempotency_key)
                if existing_operation is not None:
                    if existing_operation.request_hash != request_hash:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='idempotency_key_conflict')
                    return self._load_operation_response(existing_operation)

                self._ensure_revision(cart, expected_revision, catalog_slug)
                product = self._hydrate_product(db, ref)
                if product.catalog_slug != catalog_slug:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='product_catalog_mismatch')
                product_colors = split_csv_values(product.colors_json or [])
                product_sizes = split_csv_values(product.sizes_json or [])
                color_value = self._normalize_variant(color, product_colors, field_name='color')
                size_value = self._normalize_variant(size, product_sizes, field_name='size')
                step = normalize_qty_step(product.quantity_step, default=1)
                quantity_value = self._normalize_quantity(quantity, step)

                self._add_or_update_item(db, cart, product, color_value, size_value, quantity_value)
                increment_catalog_revision(cart, catalog_slug)
                db.flush()
                response = self._serialize_cart(cart, catalog_slug, db)
                self._store_operation(
                    db,
                    user_id=user_id,
                    key=idempotency_key,
                    operation='add_item',
                    request_hash=request_hash,
                    cart_revision=catalog_revision(cart, catalog_slug),
                    response=response,
                )
                db.flush()
                return response
        except IntegrityError:
            db.rollback()
            existing_operation = db.scalar(
                select(CartOperation).where(CartOperation.user_id == user_id, CartOperation.idempotency_key == idempotency_key)
            )
            if existing_operation and existing_operation.request_hash == request_hash:
                return self._load_operation_response(existing_operation)
            raise

    def update_item(
        self,
        db: Session,
        *,
        user_id: int,
        item_id: int,
        idempotency_key: str,
        quantity: int,
        ignore_quantity_step: bool = False,
        expected_revision: int | None = None,
        catalog_slug: str = 'villas',
    ) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        payload = {'catalog_slug': catalog_slug, 'item_id': item_id, 'quantity': quantity, 'ignore_quantity_step': bool(ignore_quantity_step), 'expected_revision': expected_revision}
        request_hash = _hash_payload('update_item', payload)
        with db.begin():
            user = self._lock_user(db, user_id)
            cart = self._lock_cart(db, user_id)
            existing_operation = self._operation_key(db, user_id, idempotency_key)
            if existing_operation is not None:
                if existing_operation.request_hash != request_hash:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='idempotency_key_conflict')
                return self._load_operation_response(existing_operation)
            item = db.get(CartItem, item_id)
            if item is None or item.cart_user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='cart_item_not_found')
            if cart_item_catalog(item) != catalog_slug:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='cart_item_not_found')
            self._ensure_revision(cart, expected_revision, catalog_slug)
            product = item.product
            if product is None or not self._product_is_available(product):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='product_not_available')
            step = 1 if ignore_quantity_step and normalize_text(user.role).casefold() in {'admin', 'developer'} else normalize_qty_step(product.quantity_step, default=1)
            quantity_value = self._normalize_quantity(quantity, step)
            item.quantity = quantity_value
            snapshot = self._cart_item_snapshot(db, user_id, product, item.color, item.size, quantity_value)
            item.unit_price_snapshot = snapshot['unit_price_snapshot']
            item.line_total_snapshot = snapshot['line_total_snapshot']
            item.product_name_snapshot = snapshot['product_name_snapshot']
            item.product_type_snapshot = snapshot['product_type_snapshot']
            item.product_image_snapshot = snapshot['product_image_snapshot']
            item.product_snapshot = snapshot['product_snapshot']
            increment_catalog_revision(cart, catalog_slug)
            db.flush()
            response = self._serialize_cart(cart, catalog_slug, db)
            self._store_operation(
                db,
                user_id=user_id,
                key=idempotency_key,
                operation='update_item',
                request_hash=request_hash,
                cart_revision=catalog_revision(cart, catalog_slug),
                response=response,
            )
            db.flush()
            return response

    def remove_item(
        self,
        db: Session,
        *,
        user_id: int,
        item_id: int,
        idempotency_key: str,
        expected_revision: int | None = None,
        catalog_slug: str = 'villas',
    ) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        payload = {'catalog_slug': catalog_slug, 'item_id': item_id, 'expected_revision': expected_revision}
        request_hash = _hash_payload('remove_item', payload)
        with db.begin():
            self._lock_user(db, user_id)
            cart = self._lock_cart(db, user_id)
            existing_operation = self._operation_key(db, user_id, idempotency_key)
            if existing_operation is not None:
                if existing_operation.request_hash != request_hash:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='idempotency_key_conflict')
                return self._load_operation_response(existing_operation)
            item = db.get(CartItem, item_id)
            if item is None or item.cart_user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='cart_item_not_found')
            if cart_item_catalog(item) != catalog_slug:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='cart_item_not_found')
            self._ensure_revision(cart, expected_revision, catalog_slug)
            db.delete(item)
            increment_catalog_revision(cart, catalog_slug)
            db.flush()
            response = self._serialize_cart(cart, catalog_slug, db)
            self._store_operation(
                db,
                user_id=user_id,
                key=idempotency_key,
                operation='remove_item',
                request_hash=request_hash,
                cart_revision=catalog_revision(cart, catalog_slug),
                response=response,
            )
            db.flush()
            return response

    def clear_cart(
        self,
        db: Session,
        *,
        user_id: int,
        idempotency_key: str,
        expected_revision: int | None = None,
        catalog_slug: str = 'villas',
    ) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        payload = {'catalog_slug': catalog_slug, 'expected_revision': expected_revision}
        request_hash = _hash_payload('clear_cart', payload)
        with db.begin():
            self._lock_user(db, user_id)
            cart = self._lock_cart(db, user_id)
            existing_operation = self._operation_key(db, user_id, idempotency_key)
            if existing_operation is not None:
                if existing_operation.request_hash != request_hash:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='idempotency_key_conflict')
                return self._load_operation_response(existing_operation)
            self._ensure_revision(cart, expected_revision, catalog_slug)
            for item in list(cart.items):
                if cart_item_catalog(item) == catalog_slug:
                    db.delete(item)
            increment_catalog_revision(cart, catalog_slug)
            db.flush()
            response = self._serialize_cart(cart, catalog_slug, db)
            self._store_operation(
                db,
                user_id=user_id,
                key=idempotency_key,
                operation='clear_cart',
                request_hash=request_hash,
                cart_revision=catalog_revision(cart, catalog_slug),
                response=response,
            )
            db.flush()
            return response

    def replace_cart(
        self,
        db: Session,
        *,
        user_id: int,
        idempotency_key: str,
        items: list[dict[str, Any]],
        expected_revision: int | None = None,
        catalog_slug: str = 'villas',
    ) -> dict[str, Any]:
        catalog_slug = normalize_cart_catalog(catalog_slug)
        payload = {'catalog_slug': catalog_slug, 'items': items, 'expected_revision': expected_revision}
        request_hash = _hash_payload('replace_cart', payload)
        with db.begin():
            self._lock_user(db, user_id)
            cart = self._lock_cart(db, user_id)
            existing_operation = self._operation_key(db, user_id, idempotency_key)
            if existing_operation is not None:
                if existing_operation.request_hash != request_hash:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='idempotency_key_conflict')
                return self._load_operation_response(existing_operation)
            self._ensure_revision(cart, expected_revision, catalog_slug)

            canonical: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in items:
                product = self._hydrate_product(db, row['ref'])
                if product.catalog_slug != catalog_slug:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='product_catalog_mismatch')
                product_colors = split_csv_values(product.colors_json or [])
                product_sizes = split_csv_values(product.sizes_json or [])
                color_value = self._normalize_variant(row.get('color'), product_colors, field_name='color')
                size_value = self._normalize_variant(row.get('size'), product_sizes, field_name='size')
                step = normalize_qty_step(product.quantity_step, default=1)
                quantity_value = self._normalize_quantity(row.get('quantity'), step)
                key = (product.ref, color_value, size_value)
                canonical[key] = {
                    'product': product,
                    'color': color_value,
                    'size': size_value,
                    'quantity': canonical.get(key, {}).get('quantity', 0) + quantity_value,
                }

            for item in list(cart.items):
                if cart_item_catalog(item) == catalog_slug:
                    db.delete(item)
            db.flush()
            for entry in canonical.values():
                product = entry['product']
                snapshot = self._cart_item_snapshot(db, user_id, product, entry['color'], entry['size'], entry['quantity'])
                cart.items.append(
                    CartItem(
                        cart_user_id=user_id,
                        product_ref=product.ref,
                        color=entry['color'],
                        size=entry['size'],
                        quantity=entry['quantity'],
                        unit_price_snapshot=snapshot['unit_price_snapshot'],
                        line_total_snapshot=snapshot['line_total_snapshot'],
                        product_name_snapshot=snapshot['product_name_snapshot'],
                        product_type_snapshot=snapshot['product_type_snapshot'],
                        product_image_snapshot=snapshot['product_image_snapshot'],
                        product_snapshot=snapshot['product_snapshot'],
                    )
                )
            increment_catalog_revision(cart, catalog_slug)
            db.flush()
            response = self._serialize_cart(cart, catalog_slug, db)
            self._store_operation(
                db,
                user_id=user_id,
                key=idempotency_key,
                operation='replace_cart',
                request_hash=request_hash,
                cart_revision=catalog_revision(cart, catalog_slug),
                response=response,
            )
            db.flush()
            return response
