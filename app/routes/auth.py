from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_db, require_user
from ..authz import current_user
from ..services import AuthService, landing_path_for_role
from .web import templates

router = APIRouter()


@router.get('/entrar', response_class=HTMLResponse)
def login_page(request: Request, user=Depends(current_user)):
    settings = get_settings()
    if user:
        return RedirectResponse(url=landing_path_for_role(user.role), status_code=303)
    return templates.TemplateResponse(request, 'login.html', {'title': f'{settings.app_name} | Login'})


@router.get('/login')
def login_alias():
    return RedirectResponse(url='/entrar', status_code=302)


@router.post('/entrar')
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    service = AuthService(settings)
    try:
        user = service.authenticate(
            db,
            username=username,
            password=password,
            ip=request.state.client_ip,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except HTTPException as exc:
        if exc.status_code == 429:
            return RedirectResponse(url='/entrar?error=too_many_attempts', status_code=303)
        raise
    if not user:
        return RedirectResponse(url='/entrar?error=invalid_credentials', status_code=303)
    session_id, csrf_token = service.create_session(
        db,
        user,
        ip=request.state.client_ip,
        user_agent=request.headers.get('user-agent'),
        request_id=getattr(request.state, 'request_id', None),
        auth_context={
            'path': str(request.url.path),
            'client_ip': request.state.client_ip,
        },
    )
    response = RedirectResponse(url=landing_path_for_role(user.role), status_code=303)
    response.set_cookie(settings.session_cookie_name, session_id, httponly=True, secure=settings.cookie_secure_flag, samesite=settings.cookie_samesite, max_age=settings.session_ttl_minutes * 60, path='/')
    response.set_cookie('villas_v2_csrf', csrf_token, httponly=False, secure=settings.cookie_secure_flag, samesite=settings.cookie_samesite, max_age=settings.session_ttl_minutes * 60, path='/')
    return response


@router.post('/logout')
def logout(
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    settings = get_settings()
    AuthService(settings).validate_csrf_submission(request, csrf_token)
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        AuthService(settings).revoke_session(db, session_id)
    response = RedirectResponse(url='/entrar', status_code=303)
    response.delete_cookie(settings.session_cookie_name, path='/')
    response.delete_cookie('villas_v2_csrf', path='/')
    return response
