from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..authz import require_admin
from ..catalog import CatalogService, normalize_qty_step, normalize_reference, normalize_season, split_csv_values, to_decimal
from ..dependencies import get_db
from ..config import get_settings
from ..media import save_uploaded_product_image
from ..models import Category, Product
from ..services import AuthService
from .web import templates

router = APIRouter()
catalog = CatalogService()


def _admin_context(request: Request, user, db: Session, *, edit_ref: str | None = None, q: str | None = None):
    categories = catalog.list_categories(db, include_inactive=True)
    stmt = catalog.list_products(db, q=q, include_inactive=True, page=1, per_page=500)
    editing_product = catalog.get_product(db, edit_ref) if edit_ref else None
    csrf_token = request.cookies.get('villas_v2_csrf', '')
    return {
        'user': user,
        'csrf_token': csrf_token,
        'categories': categories,
        'page_data': stmt,
        'editing_product': editing_product,
        'query': q or '',
        'catalog_counts': catalog.catalog_counts(db),
    }


def _require_admin_csrf(request: Request, csrf_token: str) -> None:
    AuthService().validate_csrf_submission(request, csrf_token)


def _save_product(db: Session, *, ref: str, name: str, product_type: str, category_slug: str | None, price: str, pvp: str | None, colors: str | None, sizes: str | None, season: str | None, qtd_step: int, sort_order: int, active: bool, manual_active: bool, description: str | None, image_payload: tuple[str, str, str, float] | None, updating: Product | None = None) -> Product:
    ref_value = normalize_reference(ref)
    if not ref_value:
        raise HTTPException(status_code=400, detail='ref_required')
    if not name.strip():
        raise HTTPException(status_code=400, detail='name_required')
    if not product_type.strip():
        raise HTTPException(status_code=400, detail='type_required')
    if qtd_step < 1:
        raise HTTPException(status_code=400, detail='qtd_step_invalid')
    if category_slug:
        category = db.get(Category, normalize_reference(category_slug))
        if category is None:
            raise HTTPException(status_code=404, detail='category_not_found')
    else:
        category = None

    product = updating or db.get(Product, ref_value)
    if product is None:
        product = Product(ref=ref_value)
        db.add(product)
    elif updating is None and product.ref != ref_value:
        raise HTTPException(status_code=409, detail='ref_exists')

    product.ref = ref_value
    product.name = name.strip()
    product.product_type = product_type.strip()
    product.category_slug = category.slug if category else None
    product.price = to_decimal(price)
    product.pvp = None if pvp in (None, '') else to_decimal(pvp)
    product.colors_json = split_csv_values(colors)
    product.sizes_json = split_csv_values(sizes)
    product.season = normalize_season(season)
    product.quantity_step = normalize_qty_step(qtd_step)
    product.sort_order = int(sort_order or 0)
    product.active = active
    product.manual_active = manual_active
    if description is not None:
        product.description = description.strip() or None
    if image_payload is not None:
        image_path, checksum, mime_type, image_zoom = image_payload
        product.image_path = image_path
        product.image_checksum = checksum
        product.image_mime_type = mime_type
    metadata = dict(product.metadata_json or {})
    metadata['source'] = 'admin'
    if image_payload is not None:
        metadata.update({'image_zoom': image_zoom, 'image_framing_version': 1})
    product.metadata_json = metadata
    db.commit()
    db.refresh(product)
    return product


@router.get('/admin/produtos', response_class=HTMLResponse)
def admin_products(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    edit: str | None = Query(default=None),
):
    return templates.TemplateResponse(request, 'admin_products.html', _admin_context(request, user, db, edit_ref=edit, q=q))


@router.post('/admin/produtos')
async def admin_create_product(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    ref: str = Form(...),
    name: str = Form(...),
    product_type: str = Form(...),
    category_slug: str | None = Form(None),
    price: str = Form(...),
    pvp: str | None = Form(None),
    colors: str | None = Form(None),
    sizes: str | None = Form(None),
    season: str | None = Form('ambos'),
    qtd_step: int = Form(12),
    sort_order: int = Form(0),
    active: str | None = Form(None),
    manual_active: str | None = Form(None),
    description: str | None = Form(None),
    image_file: UploadFile | None = File(None),
):
    _require_admin_csrf(request, csrf_token)
    image_payload = None
    if image_file and image_file.filename:
        image_payload = await save_uploaded_product_image(image_file, get_settings().media_root, ref)
    _save_product(
        db,
        ref=ref,
        name=name,
        product_type=product_type,
        category_slug=category_slug,
        price=price,
        pvp=pvp,
        colors=colors,
        sizes=sizes,
        season=season,
        qtd_step=qtd_step,
        sort_order=sort_order,
        active=active is not None,
        manual_active=manual_active is not None,
        description=description,
        image_payload=image_payload,
    )
    return RedirectResponse(url='/admin/produtos?created=1', status_code=303)


@router.post('/admin/produtos/{ref}')
async def admin_update_product(
    request: Request,
    ref: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    new_ref: str = Form(...),
    name: str = Form(...),
    product_type: str = Form(...),
    category_slug: str | None = Form(None),
    price: str = Form(...),
    pvp: str | None = Form(None),
    colors: str | None = Form(None),
    sizes: str | None = Form(None),
    season: str | None = Form('ambos'),
    qtd_step: int = Form(12),
    sort_order: int = Form(0),
    active: str | None = Form(None),
    manual_active: str | None = Form(None),
    description: str | None = Form(None),
    image_file: UploadFile | None = File(None),
):
    _require_admin_csrf(request, csrf_token)
    existing = db.get(Product, normalize_reference(ref))
    if existing is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    normalized_new_ref = normalize_reference(new_ref)
    if not normalized_new_ref:
        raise HTTPException(status_code=400, detail='ref_required')
    if normalized_new_ref != existing.ref and db.get(Product, normalized_new_ref) is not None:
        raise HTTPException(status_code=409, detail='ref_exists')
    image_payload = None
    if image_file and image_file.filename:
        image_payload = await save_uploaded_product_image(image_file, get_settings().media_root, normalized_new_ref)
    _save_product(
        db,
        ref=normalized_new_ref,
        name=name,
        product_type=product_type,
        category_slug=category_slug,
        price=price,
        pvp=pvp,
        colors=colors,
        sizes=sizes,
        season=season,
        qtd_step=qtd_step,
        sort_order=sort_order,
        active=active is not None,
        manual_active=manual_active is not None,
        description=description,
        image_payload=image_payload,
        updating=existing,
    )
    return RedirectResponse(url='/admin/produtos?updated=1', status_code=303)


@router.post('/admin/produtos/{ref}/toggle')
def admin_toggle_product(
    request: Request,
    ref: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    _require_admin_csrf(request, csrf_token)
    product = db.get(Product, normalize_reference(ref))
    if product is None:
        raise HTTPException(status_code=404, detail='product_not_found')
    product.active = not product.active
    db.commit()
    return RedirectResponse(url='/admin/produtos?updated=1', status_code=303)


@router.get('/admin/categorias', response_class=HTMLResponse)
def admin_categories(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        'admin_categories.html',
        {
            'user': user,
            'csrf_token': request.cookies.get('villas_v2_csrf', ''),
            'categories': catalog.list_categories(db, include_inactive=True),
            'catalog_counts': catalog.catalog_counts(db),
        },
    )


@router.post('/admin/categorias')
def admin_create_category(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    slug: str = Form(...),
    label: str = Form(...),
    sort_order: int = Form(0),
    active: str | None = Form(None),
):
    _require_admin_csrf(request, csrf_token)
    slug_value = normalize_reference(slug)
    if not slug_value:
        raise HTTPException(status_code=400, detail='slug_required')
    category = db.get(Category, slug_value)
    if category is None:
        category = Category(slug=slug_value, label=label.strip(), sort_order=int(sort_order or 0), active=active is not None, visible_on_site=active is not None)
        db.add(category)
    else:
        category.label = label.strip()
        category.sort_order = int(sort_order or 0)
        category.active = active is not None
        category.visible_on_site = active is not None
    db.commit()
    return RedirectResponse(url='/admin/categorias?updated=1', status_code=303)


@router.post('/admin/categorias/{slug}/toggle')
def admin_toggle_category(
    request: Request,
    slug: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
):
    _require_admin_csrf(request, csrf_token)
    category = db.get(Category, normalize_reference(slug))
    if category is None:
        raise HTTPException(status_code=404, detail='category_not_found')
    category.active = not category.active
    category.visible_on_site = category.active
    db.commit()
    return RedirectResponse(url='/admin/categorias?updated=1', status_code=303)
