from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..authz import require_client_or_above
from ..cart_service import CartService
from ..cart_catalog import normalize_cart_catalog
from ..catalog_access import can_access_catalog
from ..dependencies import get_db
from ..config import get_settings
from ..services import AuthService
from ..schemas import CartDeleteInput, CartItemUpdateInput, CartMutationInput, CartReplaceInput
from .web import templates

router = APIRouter()
service = CartService()
auth = AuthService(get_settings())


def _wants_json(request: Request, output: str | None = None) -> bool:
    if output == 'json':
        return True
    accept = request.headers.get('accept', '')
    return 'application/json' in accept.lower()


def _allowed_catalog(user, value: str | None) -> str:
    catalog_slug = normalize_cart_catalog(value)
    if not can_access_catalog(user, catalog_slug):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail='catalog_forbidden')
    return catalog_slug


def _cart_context(request: Request, user, db: Session, catalog_slug: str) -> dict[str, object]:
    cart = service.get_cart(db, user.id, catalog_slug)
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'cart': cart,
        'cart_count': cart['units'],
    }


@router.get('/me/cart')
def cart_get(
    request: Request,
    output: str | None = Query(default=None),
    catalog: str = Query(default='villas'),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    catalog_slug = _allowed_catalog(user, catalog)
    cart = service.get_cart(db, user.id, catalog_slug)
    if _wants_json(request, output):
        return JSONResponse({'ok': True, 'cart': cart})
    return templates.TemplateResponse(request, 'cart.html', _cart_context(request, user, db, catalog_slug))


@router.put('/me/cart')
def cart_replace(
    request: Request,
    payload: CartReplaceInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    catalog_slug = _allowed_catalog(user, payload.catalog_slug)
    cart = service.replace_cart(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        items=[item.model_dump() for item in payload.items],
        expected_revision=payload.cart_revision,
        catalog_slug=catalog_slug,
    )
    return JSONResponse({'ok': True, 'cart': cart})


@router.delete('/me/cart')
def cart_clear(
    request: Request,
    payload: CartDeleteInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    catalog_slug = _allowed_catalog(user, payload.catalog_slug)
    cart = service.clear_cart(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        expected_revision=payload.cart_revision,
        catalog_slug=catalog_slug,
    )
    return JSONResponse({'ok': True, 'cart': cart})


@router.post('/me/cart/items')
def cart_add_item(
    request: Request,
    payload: CartMutationInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    catalog_slug = _allowed_catalog(user, payload.catalog_slug)
    cart = service.add_item(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        ref=payload.ref,
        color=payload.color,
        size=payload.size,
        quantity=payload.quantity,
        expected_revision=payload.cart_revision,
        catalog_slug=catalog_slug,
    )
    return JSONResponse({'ok': True, 'cart': cart})


@router.patch('/me/cart/items/{item_id}')
def cart_update_item(
    request: Request,
    item_id: int,
    payload: CartItemUpdateInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    catalog_slug = _allowed_catalog(user, payload.catalog_slug)
    cart = service.update_item(
        db,
        user_id=user.id,
        item_id=item_id,
        idempotency_key=payload.idempotency_key,
        quantity=payload.quantity,
        ignore_quantity_step=payload.ignore_quantity_step and user.role in {'admin', 'developer'},
        expected_revision=payload.cart_revision,
        catalog_slug=catalog_slug,
    )
    return JSONResponse({'ok': True, 'cart': cart})


@router.delete('/me/cart/items/{item_id}')
def cart_remove_item(
    request: Request,
    item_id: int,
    payload: CartDeleteInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    catalog_slug = _allowed_catalog(user, payload.catalog_slug)
    cart = service.remove_item(
        db,
        user_id=user.id,
        item_id=item_id,
        idempotency_key=payload.idempotency_key,
        expected_revision=payload.cart_revision,
        catalog_slug=catalog_slug,
    )
    return JSONResponse({'ok': True, 'cart': cart})
