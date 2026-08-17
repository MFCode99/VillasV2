from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..authz import current_user
from ..dependencies import require_user
from ..services import landing_path_for_role

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')


@router.get('/', response_class=HTMLResponse)
def root(request: Request, user=Depends(current_user)):
    if user:
        return RedirectResponse(url=landing_path_for_role(user.role), status_code=303)
    return RedirectResponse(url='/entrar', status_code=303)


@router.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(require_user)):
    return RedirectResponse(url='/catalogo', status_code=303)
