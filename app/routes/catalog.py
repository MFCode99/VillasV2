from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..cart_service import CartService
from ..catalog import CatalogService
from ..dependencies import get_db
from ..dependencies import require_user
from .web import templates

router = APIRouter()
catalog = CatalogService()
cart_service = CartService()


def _parse_bool_flag(value: str | bool | None) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    normalized = value.strip().casefold()
    if not normalized:
        return False
    return normalized in {'1', 'true', 'yes', 'on'}


def _catalog_context(request: Request, user, db: Session, *, q: str | None, ref: str | None, category: str | None, season: str | None, sort: str | None, view: str | None, page: int, show_inactive: bool):
    include_inactive = show_inactive and user.role in {'admin', 'developer'}
    categories = catalog.list_categories(db, include_inactive=include_inactive)
    cart_summary = cart_service.get_cart(db, user.id)
    page_data = catalog.list_products(
        db,
        q=q,
        ref=ref,
        category=category,
        season=season,
        sort=sort,
        include_inactive=include_inactive,
        page=page,
        per_page=12,
    )
    return {
        'user': user,
        'csrf_token': request.cookies.get('villas_v2_csrf', ''),
        'categories': categories,
        'page_data': page_data,
        'catalog_counts': catalog.catalog_counts(db),
        'cart_summary': cart_summary,
        'query': {
            'q': q or '',
            'ref': ref or '',
            'category': category or '',
            'season': season or '',
            'sort': sort or 'ref_asc',
            'view': view or 'grid',
            'show_inactive': '1' if show_inactive else '',
            'page': page,
        },
        'include_inactive': include_inactive,
        'can_manage_products': user.role in {'admin', 'developer'},
    }


@router.get('/catalogo', response_class=HTMLResponse)
def catalog_home(
    request: Request,
    user=Depends(require_user),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    ref: str | None = Query(default=None),
    category: str | None = Query(default=None),
    season: str | None = Query(default=None),
    sort: str | None = Query(default='ref_asc'),
    view: str | None = Query(default='grid'),
    page: int = Query(default=1, ge=1),
    show_inactive: str | bool | None = Query(default=None),
):
    context = _catalog_context(request, user, db, q=q, ref=ref, category=category, season=season, sort=sort, view=view, page=page, show_inactive=_parse_bool_flag(show_inactive))
    return templates.TemplateResponse(request, 'catalog.html', context)


@router.get('/catalogo/list', response_class=HTMLResponse)
def catalog_list(
    request: Request,
    user=Depends(require_user),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    ref: str | None = Query(default=None),
    category: str | None = Query(default=None),
    season: str | None = Query(default=None),
    sort: str | None = Query(default='ref_asc'),
    view: str | None = Query(default='grid'),
    page: int = Query(default=1, ge=1),
    show_inactive: str | bool | None = Query(default=None),
):
    context = _catalog_context(request, user, db, q=q, ref=ref, category=category, season=season, sort=sort, view=view, page=page, show_inactive=_parse_bool_flag(show_inactive))
    return templates.TemplateResponse(request, 'partials/catalog_results.html', context)


@router.get('/catalogo/produto/{ref}', response_class=HTMLResponse)
def catalog_detail(
    request: Request,
    ref: str,
    panel: int = Query(default=0),
    user=Depends(require_user),
    db: Session = Depends(get_db),
):
    include_inactive = user.role in {'admin', 'developer'}
    product = catalog.get_product(db, ref)
    if not product or ((not include_inactive) and (not product.active or not product.manual_active or (product.category and not product.category.active))):
        raise HTTPException(status_code=404, detail='product_not_found')
    template_name = 'partials/product_detail_panel.html' if panel else 'catalog_detail.html'
    return templates.TemplateResponse(
        request,
        template_name,
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'product': product,
            'include_inactive': include_inactive,
            'cart_summary': cart_service.get_cart(db, user.id),
            'can_manage_products': user.role in {'admin', 'developer'},
            'can_add_to_cart': user.role in {'client', 'admin', 'developer'},
            'panel': bool(panel),
        },
    )
