from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..admin_business import AdminStatisticsService, ExcelExportService, WarningService
from ..authz import require_admin
from ..config import get_settings
from ..dependencies import get_db
from ..models import Catalog
from ..order_service import OrderService
from ..services import AuthService, UserAdminService
from .web import templates

router = APIRouter()
user_service = UserAdminService()
order_service = OrderService()
stats_service = AdminStatisticsService()
warning_service = WarningService()
excel_service = ExcelExportService()
settings = get_settings()


def _business_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(settings.business_timezone))
    except Exception:
        return datetime.now(UTC)


def _admin_shell_context(request: Request, user, db: Session) -> dict[str, object]:
    metrics = stats_service.dashboard_metrics(db)
    monthly = stats_service.monthly_series(db, months=6)
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'metrics': metrics,
        'monthly_series': monthly,
        'warning_count': metrics.warning_count,
        'recent_orders': order_service.list_admin_orders(db, limit=8),
        'recent_customers': user_service.list_users(db, limit=8, role='client'),
    }


def _customer_context(
    request: Request,
    user,
    db: Session,
    *,
    q: str | None = None,
    role: str | None = None,
    status_filter: str | None = None,
) -> dict[str, object]:
    selected_role = role if role in {'client', 'admin'} else None
    selected_status = status_filter if status_filter in {'active', 'inactive'} else 'all'
    active = True if selected_status == 'active' else False if selected_status == 'inactive' else None
    customers = user_service.list_users(db, limit=300, q=q, role=selected_role, active=active)
    all_users = user_service.list_users(db, limit=1000)
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'customers': customers,
        'query': q or '',
        'selected_role': selected_role or 'all',
        'selected_status': selected_status,
        'counts': {
            'all': len(all_users),
            'client': sum(item.role == 'client' for item in all_users),
            'admin': sum(item.role == 'admin' for item in all_users),
        },
        'all_clients_active': bool(counts_client := [item for item in all_users if item.role == 'client']) and all(item.active for item in counts_client),
        'warning_count': warning_service.count_warnings(db),
    }


def _customer_detail_context(request: Request, user, db: Session, customer_id: int) -> dict[str, object]:
    customer = user_service.get_user(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail='customer_not_found')
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'customer': customer,
        'orders': order_service.list_client_orders(db, user_id=customer.id),
        'warnings': [warning for warning in warning_service.list_warnings(db) if warning.entity_id == customer.id],
        'customer_warning_keys': warning_service.customer_warning_keys(db, customer.id),
    }


@router.get('/admin', response_class=HTMLResponse)
def admin_home(request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, 'admin_dashboard.html', _admin_shell_context(request, user, db))


@router.get('/admin/estatisticas', response_class=HTMLResponse)
def admin_statistics(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if year is None or month is None:
        current_period = _business_now()
        year = year or current_period.year
        month = month or current_period.month
    report = stats_service.monthly_report(db, year=year, month=month)
    return templates.TemplateResponse(
        request,
        'admin_statistics.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'report': report,
            'monthly_series': stats_service.monthly_series(db, months=12),
            'query': {'year': year, 'month': month},
            'metrics': stats_service.dashboard_metrics(db),
        },
    )


@router.get('/admin/estatisticas/export.xlsx')
def admin_statistics_export(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    scope: str = Query(default='month', pattern='^(month|year)$'),
    catalog: str | None = Query(default=None),
):
    if year is None or month is None:
        current_period = _business_now()
        year = year or current_period.year
        month = month or current_period.month
    catalog_value = catalog.strip().casefold() if catalog else None
    if catalog_value is not None and db.get(Catalog, catalog_value) is None:
        raise HTTPException(status_code=400, detail='catalog_not_found')
    if scope == 'year':
        report = stats_service.annual_report(db, year=year, catalog=catalog_value)
        orders = stats_service.year_detail(db, year=year, catalog=catalog_value)['orders']
    else:
        report = stats_service.monthly_report(db, year=year, month=month, catalog=catalog_value)
        orders = stats_service.period_detail(db, year=year, month=month, catalog=catalog_value)['orders']
    payload = excel_service.build_stats_export(report=report, orders=orders)
    period_suffix = f'{year:04d}' if scope == 'year' else f'{year:04d}-{month:02d}'
    filename = f'vitor-gouveia-stats-{catalog_value or "todos"}-{period_suffix}.xlsx'
    return Response(
        content=payload,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.get('/admin/users', response_class=HTMLResponse)
@router.get('/admin/clientes', response_class=HTMLResponse)
def admin_customers(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
):
    return templates.TemplateResponse(
        request,
        'admin_customers.html',
        _customer_context(request, user, db, q=q, role=role, status_filter=status_filter),
    )


@router.get('/admin/clientes/{user_id}', response_class=HTMLResponse)
def admin_customer_detail(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(request, 'admin_customer_detail.html', _customer_detail_context(request, user, db, user_id))


@router.post('/admin/clientes/{user_id}')
def admin_customer_update(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    full_name: str = Form(...),
    email: str | None = Form(None),
    nif: str | None = Form(None),
    company_name: str | None = Form(None),
    phone: str | None = Form(None),
    address_line1: str | None = Form(None),
    address_line2: str | None = Form(None),
    postal_code: str | None = Form(None),
    city: str | None = Form(None),
    country: str | None = Form(None),
    role: str | None = Form(None),
    active: str | None = Form(None),
    admin_notes: str | None = Form(None),
):
    AuthService().validate_csrf_submission(request, csrf_token)
    user_service.update_user(
        db,
        user_id,
        full_name=full_name,
        email=email,
        nif=nif,
        company_name=company_name,
        phone=phone,
        address_line1=address_line1,
        address_line2=address_line2,
        postal_code=postal_code,
        city=city,
        country=country,
        role=role,
        active=active is not None,
        admin_notes=admin_notes,
    )
    return RedirectResponse(url=f'/admin/clientes/{user_id}?updated=1', status_code=303)


@router.post('/admin/users')
def admin_create_user(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form('client'),
    email: str | None = Form(None),
    nif: str | None = Form(None),
    company_name: str | None = Form(None),
    phone: str | None = Form(None),
    address_line1: str | None = Form(None),
    address_line2: str | None = Form(None),
    postal_code: str | None = Form(None),
    city: str | None = Form(None),
    country: str | None = Form(None),
    active: str | None = Form(None),
):
    auth = AuthService()
    auth.validate_csrf_submission(request, csrf_token)
    user_service.create_user(
        db,
        username=username,
        password=password,
        full_name=full_name,
        role=role,
        email=email,
        nif=nif,
        company_name=company_name,
        phone=phone,
        address_line1=address_line1,
        address_line2=address_line2,
        postal_code=postal_code,
        city=city,
        country=country,
        active=active is not None,
    )
    return RedirectResponse(url='/admin/users?created=1', status_code=303)


@router.post('/admin/users/{user_id}/toggle')
def admin_toggle_user(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    auth = AuthService()
    auth.validate_csrf_submission(request, csrf_token)
    target = user_service.get_user(db, user_id)
    if target is not None:
        user_service.set_active(db, user_id, not target.active)
    return RedirectResponse(url='/admin/clientes?updated=1', status_code=303)


@router.post('/admin/users/clients/toggle-all')
def admin_toggle_all_clients(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    active: str = Form(...),
):
    AuthService().validate_csrf_submission(request, csrf_token)
    user_service.set_all_clients_active(db, active == 'true')
    return RedirectResponse(url='/admin/clientes?bulk_updated=1', status_code=303)


@router.post('/admin/users/{user_id}/password')
def admin_reset_user_password(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    password: str = Form(...),
):
    AuthService().validate_csrf_submission(request, csrf_token)
    user_service.reset_password(db, user_id, password)
    AuthService().revoke_user_sessions(db, user_id)
    return RedirectResponse(url=f'/admin/clientes/{user_id}?password_updated=1', status_code=303)


@router.post('/admin/users/{user_id}/delete')
def admin_delete_user(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    AuthService().validate_csrf_submission(request, csrf_token)
    if user.id == user_id:
        return RedirectResponse(url=f'/admin/clientes/{user_id}?delete_blocked=self', status_code=303)
    if not user_service.delete_user(db, user_id):
        return RedirectResponse(url=f'/admin/clientes/{user_id}?delete_blocked=history', status_code=303)
    return RedirectResponse(url='/admin/clientes?deleted=1', status_code=303)


@router.post('/admin/users/{user_id}/role')
def admin_set_role(
    request: Request,
    user_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    role: str = Form(...),
):
    auth = AuthService()
    auth.validate_csrf_submission(request, csrf_token)
    user_service.set_role(db, user_id, role)
    return RedirectResponse(url='/admin/clientes?updated=1', status_code=303)


@router.get('/admin/avisos', response_class=HTMLResponse)
def admin_warnings(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    warnings = warning_service.list_warnings(db)
    return templates.TemplateResponse(
        request,
        'admin_warnings.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'warnings': warnings,
            'warning_count': len(warnings),
            'metrics': stats_service.dashboard_metrics(db),
        },
    )


@router.post('/admin/avisos/{warning_key}/ignore')
def admin_ignore_warning(
    request: Request,
    warning_key: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    reason: str | None = Form(None),
):
    AuthService().validate_csrf_submission(request, csrf_token)
    warning_service.ignore_warning(db, warning_key=warning_key, ignored_by_user_id=user.id, reason=reason)
    return RedirectResponse(url='/admin/avisos?ignored=1', status_code=303)
