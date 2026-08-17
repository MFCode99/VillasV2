from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .catalog import split_csv_values
from .formatters import format_datetime, format_money
from .logging_conf import configure_logging
from .middleware import RequestContextMiddleware
from .routes.catalog import router as catalog_router
from .routes.cart import router as cart_router
from .routes.orders import router as orders_router
from .routes.catalog_admin import router as catalog_admin_router
from .routes.admin import router as admin_router
from .routes.auth import router as auth_router
from .routes.health import router as health_router
from .routes.developer import router as developer_router
from .routes.web import router as web_router, templates
from .routes.api import router as api_router

settings = get_settings()
configure_logging(settings)
settings.media_root.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version='0.1.0')
app.state.settings = settings
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_url],
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['*'],
)
app.mount('/static', StaticFiles(directory='app/static'), name='static')
app.mount('/media', StaticFiles(directory=str(settings.media_root)), name='media')
frontend_dist = Path('frontend/dist')
if frontend_dist.exists():
    app.mount('/assets', StaticFiles(directory=str(frontend_dist / 'assets')), name='frontend-assets')


@app.get('/nova', include_in_schema=False)
@app.get('/nova/{frontend_path:path}', include_in_schema=False)
def legacy_preview_redirect(frontend_path: str = ''):
    return RedirectResponse(url='/', status_code=308)


def vue_frontend(frontend_path: str = ''):
    index_file = frontend_dist / 'index.html'
    if not index_file.exists():
        return JSONResponse(status_code=503, content={'detail': 'frontend_not_built'})
    return FileResponse(index_file)


# These are registered before the legacy HTML routers so the Vue application is
# the public portal. The remaining legacy routes only provide backend actions
# still used by the new interface (PDFs, exports and order/cart operations).
for frontend_path in (
    '/',
    '/login',
    '/catalogo',
    '/catalogo/{frontend_path:path}',
    '/carrinho',
    '/encomendas',
    '/encomendas/{frontend_path:path}',
    '/admin',
    '/admin/utilizadores',
    '/admin/utilizadores/{frontend_path:path}',
    '/admin/produtos',
    '/admin/categorias',
    '/admin/encomendas',
    '/admin/encomendas/nova',
    '/admin/encomendas/{frontend_path:path}',
    '/admin/avisos',
    '/admin/estatisticas',
):
    app.add_api_route(frontend_path, vue_frontend, methods=['GET'], include_in_schema=False)

templates.env.filters['money'] = format_money
templates.env.filters['datetime_pt'] = format_datetime
templates.env.filters['choices'] = split_csv_values

app.include_router(health_router)
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(catalog_admin_router)
app.include_router(admin_router)
app.include_router(developer_router)
app.include_router(web_router)


@app.on_event('startup')
def startup() -> None:
    settings.media_root.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    (settings.media_root / 'products').mkdir(parents=True, exist_ok=True)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code in {303, 307, 308}:
        headers = exc.headers or {}
        return RedirectResponse(url=str(headers.get('location', '/entrar')), status_code=exc.status_code)
    if 'text/html' in request.headers.get('accept', ''):
        return templates.TemplateResponse(request, 'error.html', {'message': exc.detail, 'status_code': exc.status_code}, status_code=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail, 'request_id': getattr(request.state, 'request_id', None)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={'detail': exc.errors(), 'request_id': getattr(request.state, 'request_id', None)})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if 'text/html' in request.headers.get('accept', ''):
        return templates.TemplateResponse(request, 'error.html', {'message': 'Internal server error', 'status_code': 500}, status_code=500)
    return JSONResponse(status_code=500, content={'detail': 'Internal server error', 'request_id': getattr(request.state, 'request_id', None)})
