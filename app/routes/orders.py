from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Form, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..authz import require_admin, require_client_or_above
from ..admin_business import AdminOrderDraftService
from ..config import get_settings
from ..dependencies import get_db
from ..email_service import EmailService, EmailSendResult
from ..catalog import CatalogService
from ..order_service import OrderService
from ..pdf_service import build_order_pdf
from ..schemas import OrderSubmitInput
from ..services import AuthService, UserAdminService
from .web import templates

router = APIRouter()
service = OrderService()
auth = AuthService(get_settings())
draft_service = AdminOrderDraftService()
catalog = CatalogService()
user_service = UserAdminService()


def _wants_json(request: Request, output: str | None = None) -> bool:
    if output == 'json':
        return True
    accept = request.headers.get('accept', '')
    return 'application/json' in accept.lower()


def _client_order_context(request: Request, user, db: Session, *, output: str | None = None):
    orders = service.list_client_orders(db, user_id=user.id)
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'orders': orders,
        'order_count': len(orders),
        'admin_view': False,
        'output': output or '',
    }


def _admin_order_context(request: Request, user, db: Session, *, q: str | None = None, status: str | None = None, date_from: str | None = None, date_to: str | None = None):
    orders = service.list_admin_orders(db, q=q, status_filter=status)
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'orders': orders,
        'order_count': len(orders),
        'admin_view': True,
        'dashboard_metrics': None,
        'query': {
            'q': q or '',
            'status': status or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
        },
        'catalog_counts': {'totalOrders': len(orders)},
    }


@router.post('/me/orders')
@router.post('/me/encomendas')
def submit_order(
    request: Request,
    payload: OrderSubmitInput = Body(...),
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    auth.validate_csrf_submission(request, request.headers.get('X-CSRF-Token'))
    customer_user_id = payload.customer_user_id
    if user.role == 'admin':
        if customer_user_id is None:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='customer_required')
        customer = user_service.get_user(db, customer_user_id)
        if customer is None or customer.role != 'client' or not customer.active:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='customer_not_available')
        # The lookup above starts SQLAlchemy's implicit read transaction; the
        # order service owns the following write transaction.
        db.rollback()
    else:
        customer_user_id = user.id
    order = service.submit_order(
        db,
        user_id=user.id,
        customer_user_id=customer_user_id,
        idempotency_key=payload.idempotency_key,
        request_id=getattr(request.state, 'request_id', None),
        cart_revision=payload.cart_revision,
        notes=payload.notes,
    )
    if order.get('emailStatus') != 'sent':
        email_result = EmailService().send_order_event(
            db,
            order=order,
            event='order_received',
            request_id=getattr(request.state, 'request_id', None),
            related_user_id=customer_user_id,
        )
    else:
        email_result = EmailSendResult(status='sent')
    order = service.get_order(db, order['id'], user_id=customer_user_id, admin=user.role == 'admin') or order
    order['emailResult'] = {
        'status': email_result.status,
        'providerMessageId': email_result.provider_message_id or '',
        'errorMessage': email_result.error_message or '',
    }
    if _wants_json(request):
        return JSONResponse(
            jsonable_encoder({'ok': True, 'order': order, 'cart': {'revision': payload.cart_revision, 'units': 0}, 'message': 'Encomenda criada.'}),
            status_code=201,
        )
    return RedirectResponse(url=order['url'], status_code=303)


@router.get('/me/orders', response_class=HTMLResponse)
@router.get('/me/encomendas', response_class=HTMLResponse)
def client_orders(
    request: Request,
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
    output: str | None = Query(default=None),
):
    context = _client_order_context(request, user, db, output=output)
    if _wants_json(request, output):
        return JSONResponse({'ok': True, 'orders': context['orders']})
    return templates.TemplateResponse(request, 'orders_list.html', context)


@router.get('/me/orders/{identifier}', response_class=HTMLResponse)
@router.get('/me/encomendas/{identifier}', response_class=HTMLResponse)
def client_order_detail(
    request: Request,
    identifier: str,
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
):
    order = service.get_order(db, identifier, user_id=user.id)
    if order is None:
        return Response('Encomenda n?o encontrada', status_code=404)
    return templates.TemplateResponse(
        request,
        'order_detail.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'order': order,
            'history': service.status_history(db, order['id']),
            'email_logs': service.email_logs(db, order['id']),
            'admin_view': False,
        },
    )


@router.get('/me/orders/{identifier}/pdf')
@router.get('/me/encomendas/{identifier}/pdf')
def client_order_pdf(
    request: Request,
    identifier: str,
    user=Depends(require_client_or_above),
    db: Session = Depends(get_db),
    hide_prices: bool = Query(default=False),
):
    order = service.get_order(db, identifier, user_id=user.id)
    if order is None:
        return Response('Encomenda n?o encontrada', status_code=404)
    pdf = build_order_pdf(order, hide_prices=hide_prices)
    filename = f"{order['publicNumber']}{'_sem_precos' if hide_prices else ''}.pdf"
    return Response(content=pdf, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/admin/orders', response_class=HTMLResponse)
@router.get('/admin/encomendas', response_class=HTMLResponse)
def admin_orders(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    return templates.TemplateResponse(
        request,
        'orders_list.html',
        _admin_order_context(request, user, db, q=q, status=status, date_from=date_from, date_to=date_to),
    )


@router.get('/admin/orders/new', response_class=HTMLResponse)
@router.get('/admin/encomendas/nova', response_class=HTMLResponse)
def admin_order_new(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    customer_q: str | None = Query(default=None),
    product_q: str | None = Query(default=None),
):
    draft = draft_service.get_active_draft(db, user.id)
    customers = []
    if customer_q:
        customers = [item for item in user_service.list_users(db, q=customer_q, role='client', limit=20)]
    else:
        customers = [item for item in user_service.list_users(db, role='client', limit=20)]
    products = catalog.list_products(db, q=product_q, include_inactive=False, page=1, per_page=20)
    return templates.TemplateResponse(
        request,
        'admin_order_new.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'draft': draft,
            'customers': customers,
            'products': products,
            'customer_q': customer_q or '',
            'product_q': product_q or '',
        },
    )


@router.post('/admin/orders/new/customer')
@router.post('/admin/encomendas/nova/cliente')
def admin_order_new_customer(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    customer_id: int = Form(...),
):
    auth.validate_csrf_submission(request, csrf_token)
    draft_service.set_customer(db, admin_user_id=user.id, customer_user_id=customer_id)
    return RedirectResponse(url='/admin/encomendas/nova?updated=1', status_code=303)


@router.post('/admin/orders/new/lines')
@router.post('/admin/encomendas/nova/linhas')
def admin_order_new_line(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    ref: str = Form(...),
    color: str | None = Form(None),
    size: str | None = Form(None),
    quantity: int = Form(1),
):
    auth.validate_csrf_submission(request, csrf_token)
    draft_service.add_line(db, admin_user_id=user.id, ref=ref, color=color, size=size, quantity=quantity)
    return RedirectResponse(url='/admin/encomendas/nova?updated=1', status_code=303)


@router.post('/admin/orders/new/lines/{line_id}/remove')
@router.post('/admin/encomendas/nova/linhas/{line_id}/remover')
def admin_order_new_line_remove(
    request: Request,
    line_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    auth.validate_csrf_submission(request, csrf_token)
    draft_service.remove_line(db, admin_user_id=user.id, line_id=line_id)
    return RedirectResponse(url='/admin/encomendas/nova?updated=1', status_code=303)


@router.post('/admin/orders/new/clear')
@router.post('/admin/encomendas/nova/limpar')
def admin_order_new_clear(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    auth.validate_csrf_submission(request, csrf_token)
    draft_service.clear(db, admin_user_id=user.id)
    return RedirectResponse(url='/admin/encomendas/nova?cleared=1', status_code=303)


@router.post('/admin/orders/new/notes')
@router.post('/admin/encomendas/nova/notas')
def admin_order_new_notes(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    notes: str | None = Form(None),
):
    auth.validate_csrf_submission(request, csrf_token)
    draft_service.set_notes(db, admin_user_id=user.id, notes=notes)
    return RedirectResponse(url='/admin/encomendas/nova?updated=1', status_code=303)


@router.post('/admin/orders/new/submit')
@router.post('/admin/encomendas/nova/criar')
def admin_order_new_submit(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    auth.validate_csrf_submission(request, csrf_token)
    order = draft_service.submit(db, admin_user_id=user.id, request_id=getattr(request.state, 'request_id', None))
    return RedirectResponse(url=f"/admin/encomendas/{order['publicNumber']}", status_code=303)


@router.get('/admin/orders/{identifier}', response_class=HTMLResponse)
@router.get('/admin/encomendas/{identifier}', response_class=HTMLResponse)
def admin_order_detail(
    request: Request,
    identifier: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = service.get_order(db, identifier, admin=True)
    if order is None:
        return Response('Encomenda n?o encontrada', status_code=404)
    return templates.TemplateResponse(
        request,
        'order_detail.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'order': order,
            'history': service.status_history(db, order['id']),
            'email_logs': service.email_logs(db, order['id']),
            'admin_view': True,
        },
    )


@router.post('/admin/orders/{identifier}/status')
@router.post('/admin/encomendas/{identifier}/status')
def admin_order_status(
    request: Request,
    identifier: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    new_status: str = Form(...),
    note: str | None = Form(None),
):
    auth.validate_csrf_submission(request, csrf_token)
    order = service.change_status(
        db,
        identifier=identifier,
        new_status=new_status,
        changed_by_user_id=user.id,
        request_id=getattr(request.state, 'request_id', None),
        note=note,
    )
    if order.get('statusChanged'):
        EmailService().send_order_event(
            db,
            order=order,
            event=f"order_{order['orderStatus']}",
            request_id=getattr(request.state, 'request_id', None),
            related_user_id=order['userId'],
        )
    return RedirectResponse(url=f"/admin/encomendas/{order['publicNumber']}?updated=1", status_code=303)


@router.get('/admin/orders/{identifier}/pdf')
@router.get('/admin/encomendas/{identifier}/pdf')
def admin_order_pdf(
    request: Request,
    identifier: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    hide_prices: bool = Query(default=False),
):
    order = service.get_order(db, identifier, admin=True)
    if order is None:
        return Response('Encomenda n?o encontrada', status_code=404)
    pdf = build_order_pdf(order, hide_prices=hide_prices)
    filename = f"{order['publicNumber']}{'_sem_precos' if hide_prices else ''}.pdf"
    return Response(content=pdf, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
