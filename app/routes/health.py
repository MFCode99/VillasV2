from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..services import HealthService

router = APIRouter()


@router.get('/health')
def health(request: Request):
    return {'status': 'ok', 'request_id': getattr(request.state, 'request_id', None)}


@router.get('/ready')
def ready(request: Request, db: Session = Depends(get_db)):
    HealthService(db).check_database()
    return {'status': 'ready', 'database': 'ok', 'request_id': getattr(request.state, 'request_id', None)}