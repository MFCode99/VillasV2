from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..authz import require_developer
from ..dependencies import get_db
from ..services import DeveloperService
from .web import templates

router = APIRouter()


@router.get('/developer', response_class=HTMLResponse)
def developer_home(request: Request, user=Depends(require_developer), db: Session = Depends(get_db)):
    service = DeveloperService()
    csrf_token = request.cookies.get('villas_v2_csrf', '')
    return templates.TemplateResponse(
        request,
        'developer.html',
        {
            'user': user,
            'csrf_token': csrf_token,
            'stats': service.dashboard_stats(db),
            'login_logs': service.login_logs(db),
            'sessions': service.recent_sessions(db),
            'site_settings': service.settings(db),
            'developer_notes': service.notes(db),
        },
    )
