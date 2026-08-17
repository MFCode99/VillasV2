from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..authz import require_client_or_above
from ..cart_service import CartService
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


def _cart_context(request: Request, user, db: Session) -> dict[str, object]:
    cart = service.get_cart(db, user.id)
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
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    cart = service.get_cart(db, user.id)
    if _wants_json(request, output):
        return JSONResponse({'ok': True, 'cart': cart})
    return templates.TemplateResponse(request, 'cart.html', _cart_context(request, user, db))


@router.put('/me/cart')
def cart_replace(
    request: Request,
    payload: CartReplaceInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token') or payload.csrf_token)
    cart = service.replace_cart(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        items=[item.model_dump() for item in payload.items],
        expected_revision=payload.cart_revision,
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
    cart = service.clear_cart(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        expected_revision=payload.cart_revision,
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
    cart = service.add_item(
        db,
        user_id=user.id,
        idempotency_key=payload.idempotency_key,
        ref=payload.ref,
        color=payload.color,
        size=payload.size,
        quantity=payload.quantity,
        expected_revision=payload.cart_revision,
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
    cart = service.update_item(
        db,
        user_id=user.id,
        item_id=item_id,
        idempotency_key=payload.idempotency_key,
        quantity=payload.quantity,
        expected_revision=payload.cart_revision,
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
    cart = service.remove_item(
        db,
        user_id=user.id,
        item_id=item_id,
        idempotency_key=payload.idempotency_key,
        expected_revision=payload.cart_revision,
    )
    return JSONResponse({'ok': True, 'cart': cart})
