from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from ..admin_business import AdminOrderDraftService, AdminStatisticsService, WarningService
from ..catalog import CatalogService, normalize_qty_step, normalize_reference, normalize_season, split_csv_values, to_decimal
from ..cart_service import CartService
from ..config import get_settings
from ..dependencies import get_db
from ..email_service import EmailService
from ..models import Category, EmailDeliveryLog, Order, OrderRequestId, Product, User
from ..media import persist_prepared_image, prepare_product_image, save_uploaded_product_image
from ..order_service import OrderService
from ..services import AuthService, UserAdminService

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
    role: str = 'client'
    active: bool = True
    admin_notes: str | None = None


class ActiveInput(BaseModel):
    active: bool


class PasswordInput(BaseModel):
    password: str = Field(min_length=8)


class SendOrderPdfInput(BaseModel):
    hide_prices: bool = False


class ProductInput(BaseModel):
    ref: str
    name: str
    product_type: str
    category_slug: str | None = None
    price: str
    pvp: str | None = None
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    season: str = 'ambos'
    quantity_step: int = Field(default=12, ge=1)
    sort_order: int = 0
    active: bool = True
    manual_active: bool = True
    description: str | None = None


class CategoryInput(BaseModel):
    slug: str
    label: str
    sort_order: int = 0
    active: bool = True


class StatusInput(BaseModel):
    status: str
    note: str | None = None


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


def _api_user(request: Request) -> User:
    user = getattr(request.state, 'current_user', None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='login_required')
    return user


def _api_admin(user: User = Depends(_api_user)) -> User:
    if user.role != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='forbidden')
    return user


def _csrf(request: Request) -> None:
    auth_service.validate_csrf_submission(request, request.headers.get('X-CSRF-Token'))


def _user_json(user: User, *, detailed: bool = False) -> dict[str, Any]:
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
    }
    if detailed:
        result.update({
            'addressLine1': user.address_line1 or '',
            'addressLine2': user.address_line2 or '',
            'postalCode': user.postal_code or '',
            'city': user.city or '',
            'country': user.country or '',
            'adminNotes': user.admin_notes or '',
        })
    return result


def _category_json(category: Category) -> dict[str, Any]:
    return {
        'slug': category.slug,
        'label': category.label,
        'sortOrder': category.sort_order,
        'active': bool(category.active),
        'visibleOnSite': bool(category.visible_on_site),
    }


def _product_json(product: Product) -> dict[str, Any]:
    return {
        'ref': product.ref,
        'name': product.name,
        'type': product.product_type,
        'categorySlug': product.category_slug,
        'categoryLabel': product.category.label if product.category else '',
        'categoryActive': bool(product.category.active) if product.category else True,
        'price': f'{product.price:.2f}',
        'pvp': f'{product.pvp:.2f}' if product.pvp is not None else None,
        'colors': split_csv_values(product.colors_json or []),
        'sizes': split_csv_values(product.sizes_json or []),
        'imageUrl': f'/media/{product.image_path}' if product.image_path else None,
        'sortOrder': product.sort_order,
        'active': bool(product.active),
        'manualActive': bool(product.manual_active),
        'season': product.season,
        'quantityStep': normalize_qty_step(product.quantity_step, 1),
        'description': product.description or '',
    }


def _json(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


@router.get('/session')
def session_state(request: Request):
    user = getattr(request.state, 'current_user', None)
    return _json({
        'authenticated': user is not None,
        'user': _user_json(user, detailed=True) if user else None,
        'csrfToken': request.cookies.get('villas_v2_csrf', ''),
    })


@router.get('/email/status')
def email_status(user: User = Depends(_api_user)):
    """Small, credential-free SMTP health signal used by the application shell."""
    return _json({'ok': EmailService().health_check()})


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
    response = _json({'ok': True, 'user': _user_json(user, detailed=True), 'csrfToken': csrf_token})
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
    category: str | None = None,
    season: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(_api_user),
):
    result = catalog_service.list_products(db, q=q, category=category, season=season, sort=sort, page=page, per_page=per_page)
    return _json({'items': [_product_json(item) for item in result.items], 'total': result.total, 'page': result.page, 'pages': result.pages, 'perPage': result.per_page, 'categories': [_category_json(item) for item in catalog_service.list_categories(db)]})


@router.get('/catalog/{ref}')
def catalog_detail(ref: str, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    product = catalog_service.get_product(db, ref)
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    return _json({'product': _product_json(product)})


@router.get('/cart')
def cart_get(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    return _json({'cart': cart_service.get_cart(db, user.id)})


@router.get('/orders')
def orders_get(db: Session = Depends(get_db), user: User = Depends(_api_user)):
    orders = order_service.list_admin_orders(db, limit=1000) if user.role == 'admin' else order_service.list_client_orders(db, user_id=user.id)
    return _json({'orders': orders})


@router.get('/orders/{identifier}')
def order_get(identifier: str, db: Session = Depends(get_db), user: User = Depends(_api_user)):
    order = order_service.get_order(db, identifier, admin=user.role == 'admin', user_id=None if user.role == 'admin' else user.id)
    if order is None:
        raise HTTPException(status_code=404, detail='order_not_found')
    return _json({'order': order, 'history': order_service.status_history(db, order['id']), 'emailLogs': order_service.email_logs(db, order['id']) if user.role == 'admin' else []})


@router.patch('/admin/orders/{identifier}/status')
def order_status(identifier: str, payload: StatusInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = order_service.change_status(db, identifier=identifier, new_status=payload.status, changed_by_user_id=user.id, request_id=getattr(request.state, 'request_id', None), note=payload.note)
    if order.get('statusChanged'):
        EmailService().send_order_event(db, order=order, event=f"order_{order['orderStatus']}", request_id=getattr(request.state, 'request_id', None), related_user_id=order['userId'])
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
    return _json({'metrics': asdict(stats_service.dashboard_metrics(db)), 'monthlySeries': [asdict(row) for row in stats_service.monthly_series(db, months=12)], 'recentOrders': order_service.list_admin_orders(db, limit=8), 'recentCustomers': [_user_json(item) for item in user_service.list_users(db, role='client', limit=8)]})


@router.get('/admin/users')
def users_list(q: str | None = None, role: str | None = None, active: bool | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    users = user_service.list_users(db, limit=1000, q=q, role=role, active=active)
    all_users = user_service.list_users(db, limit=2000)
    clients = [item for item in all_users if item.role == 'client']
    return _json({'users': [_user_json(item) for item in users], 'counts': {'all': len(all_users), 'client': len(clients), 'admin': sum(item.role == 'admin' for item in all_users), 'active': sum(item.active for item in all_users), 'inactive': sum(not item.active for item in all_users)}, 'allClientsActive': bool(clients) and all(item.active for item in clients)})


@router.post('/admin/users')
def user_create(payload: UserInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail='username_and_password_required')
    created = user_service.create_user(db, username=payload.username, password=payload.password, full_name=payload.full_name, role=payload.role, email=payload.email, nif=payload.nif, company_name=payload.company_name, phone=payload.phone, address_line1=payload.address_line1, address_line2=payload.address_line2, postal_code=payload.postal_code, city=payload.city, country=payload.country, active=payload.active)
    email_result = EmailService().send_user_created(db, user=created, password=payload.password, request_id=getattr(request.state, 'request_id', None))
    return _json({'ok': True, 'user': _user_json(created, detailed=True), 'emailStatus': email_result.status}, 201)


@router.get('/admin/users/{user_id}')
def user_detail(user_id: int, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    target = user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail='user_not_found')
    return _json({'user': _user_json(target, detailed=True), 'orders': order_service.list_client_orders(db, user_id=target.id), 'warnings': [asdict(item) for item in warning_service.list_warnings(db) if item.entity_id == target.id]})


@router.put('/admin/users/{user_id}')
def user_update(user_id: int, payload: UserInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    updated = user_service.update_user(db, user_id, full_name=payload.full_name, email=payload.email, nif=payload.nif, company_name=payload.company_name, phone=payload.phone, address_line1=payload.address_line1, address_line2=payload.address_line2, postal_code=payload.postal_code, city=payload.city, country=payload.country, role=payload.role, active=payload.active, admin_notes=payload.admin_notes)
    return _json({'ok': True, 'user': _user_json(updated, detailed=True)})


@router.patch('/admin/users/{user_id}/active')
def user_active(user_id: int, payload: ActiveInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    updated = user_service.set_active(db, user_id, payload.active)
    return _json({'ok': True, 'user': _user_json(updated)})


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


@router.post('/admin/users/{user_id}/orders/{identifier}/email-pdf')
def order_send_pdf_to_user(user_id: int, identifier: str, payload: SendOrderPdfInput, request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    target = user_service.get_user(db, user_id)
    order = order_service.get_order(db, identifier, admin=True)
    if target is None or order is None or order.get('userId') != user_id:
        raise HTTPException(status_code=404, detail='order_not_found')
    result = EmailService().send_order_pdf(
        db, order=order, recipient=str(target.email or ''), hide_prices=payload.hide_prices,
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
def admin_catalog(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    page = catalog_service.list_products(db, q=q, include_inactive=True, page=1, per_page=500)
    return _json({'products': [_product_json(item) for item in page.items], 'categories': [_category_json(item) for item in catalog_service.list_categories(db, include_inactive=True)], 'counts': catalog_service.catalog_counts(db)})


def _save_product_input(db: Session, payload: ProductInput, product: Product | None = None, *, commit: bool = True) -> Product:
    ref = normalize_reference(payload.ref)
    if not ref or not payload.name.strip() or not payload.product_type.strip():
        raise HTTPException(status_code=400, detail='product_required_fields')
    category = db.get(Category, payload.category_slug) if payload.category_slug else None
    if payload.category_slug and category is None:
        raise HTTPException(status_code=404, detail='category_not_found')
    if payload.active and category is not None and not category.active:
        raise HTTPException(status_code=409, detail='category_inactive')
    target = product or db.get(Product, ref)
    if target is None:
        target = Product(ref=ref)
        db.add(target)
    elif product is None:
        raise HTTPException(status_code=409, detail='ref_exists')
    target.name = payload.name.strip()
    target.product_type = payload.product_type.strip()
    target.category_slug = payload.category_slug or None
    target.price = to_decimal(payload.price)
    target.pvp = None if payload.pvp in (None, '') else to_decimal(payload.pvp)
    target.colors_json = split_csv_values(payload.colors)
    target.sizes_json = split_csv_values(payload.sizes)
    target.season = normalize_season(payload.season)
    target.quantity_step = payload.quantity_step
    target.sort_order = payload.sort_order
    target.active = payload.active
    target.manual_active = payload.manual_active
    target.description = (payload.description or '').strip() or None
    if commit:
        db.commit()
        db.refresh(target)
    else:
        db.flush()
    return target


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
        db.commit()
        db.refresh(saved)
        return _json({'ok': True, 'product': _product_json(saved)}, 200 if original_ref else 201)
    except Exception:
        db.rollback()
        if created_file and absolute_path is not None and absolute_path.exists():
            absolute_path.unlink()
        raise


@router.post('/admin/products/{ref}/image')
async def product_image(ref: str, request: Request, image: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    image_path, checksum, mime_type = await save_uploaded_product_image(image, settings.media_root, product.ref)
    product.image_path = image_path
    product.image_checksum = checksum
    product.image_mime_type = mime_type
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
    category = db.get(Category, slug) or Category(slug=slug)
    if category not in db:
        db.add(category)
    category.label = payload.label.strip()
    category.sort_order = payload.sort_order
    category.active = payload.active
    category.visible_on_site = payload.active
    db.commit()
    db.refresh(category)
    return _json({'ok': True, 'category': _category_json(category)})


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
def statistics_get(year: int = Query(default=datetime.utcnow().year), month: int = Query(default=datetime.utcnow().month, ge=1, le=12), db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    return _json({'report': asdict(stats_service.monthly_report(db, year=year, month=month)), 'series': [asdict(item) for item in stats_service.monthly_series(db, months=12)], 'metrics': asdict(stats_service.dashboard_metrics(db))})


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
    return _json({'draft': asdict(draft_service.set_notes(db, admin_user_id=user.id, notes=payload.notes))})


@router.delete('/admin/order-draft')
def draft_clear(request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    return _json({'draft': asdict(draft_service.clear(db, admin_user_id=user.id))})


@router.post('/admin/order-draft/submit')
def draft_submit(request: Request, db: Session = Depends(get_db), user: User = Depends(_api_admin)):
    _csrf(request)
    order = draft_service.submit(db, admin_user_id=user.id, request_id=getattr(request.state, 'request_id', None))
    return _json({'ok': True, 'order': order}, 201)
