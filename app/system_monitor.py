from __future__ import annotations

import json
import logging
import shutil
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .email_service import EmailService
from .models import SiteSetting, User
from .security import utcnow

logger = logging.getLogger(__name__)
MONITOR_STATE_KEY = 'monitor.last_state'
MONITOR_RUN_KEY = 'monitor.last_run'


def _set_setting(db: Session, key: str, value: dict) -> None:
    serialized = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
    setting = db.get(SiteSetting, key)
    if setting is None:
        db.add(SiteSetting(key=key, value=serialized))
    else:
        setting.value = serialized


def _get_setting(db: Session, key: str) -> dict:
    setting = db.get(SiteSetting, key)
    if setting is None:
        return {}
    try: return json.loads(setting.value)
    except (TypeError, ValueError): return {}


def monitor_snapshot(db: Session, settings: Settings | None = None, email_service: EmailService | None = None) -> dict:
    settings = settings or get_settings()
    email_service = email_service or EmailService(settings=settings)
    checks: dict[str, dict] = {}
    try:
        db.execute(select(1)).scalar_one()
        checks['database'] = {'ok': True}
    except Exception as exc:
        checks['database'] = {'ok': False, 'message': f'Base de dados indisponível ({type(exc).__name__})'}
    try:
        usage = shutil.disk_usage(settings.media_root.resolve())
        free_percent = round(usage.free / usage.total * 100, 1)
        checks['storage'] = {'ok': free_percent >= 15, 'freePercent': free_percent, 'message': f'Espaço livre no servidor: {free_percent}%'}
    except OSError as exc:
        checks['storage'] = {'ok': False, 'message': f'Armazenamento indisponível ({type(exc).__name__})'}
    checks['email'] = {'ok': email_service.health_check(), 'message': 'Não foi possível autenticar o serviço de email'}
    ready_url = f"{settings.public_url.rstrip('/')}/ready"
    try:
        request = Request(ready_url, headers={'User-Agent': 'VillasV2-Monitor/1.0'})
        with urlopen(request, timeout=12) as response:
            checks['portal'] = {'ok': response.status == 200, 'status': response.status, 'message': f'Portal respondeu com HTTP {response.status}'}
    except Exception as exc:
        checks['portal'] = {'ok': False, 'message': f'Portal público indisponível ({type(exc).__name__})'}
    issues = [value['message'] for value in checks.values() if not value.get('ok')]
    return {'ok': not issues, 'checkedAt': utcnow().isoformat(), 'checks': checks, 'issues': issues}


def run_monitor(db: Session, settings: Settings | None = None, email_service: EmailService | None = None) -> dict:
    settings = settings or get_settings()
    email_service = email_service or EmailService(settings=settings)
    previous = _get_setting(db, MONITOR_STATE_KEY)
    snapshot = monitor_snapshot(db, settings, email_service)
    previous_signature = sorted(previous.get('issues') or [])
    current_signature = sorted(snapshot['issues'])
    changed = previous_signature != current_signature
    recipients = db.scalars(select(User.email).where(User.active.is_(True), User.role == 'developer', User.email.is_not(None))).all()
    if not recipients:
        recipients = db.scalars(select(User.email).where(User.active.is_(True), User.role == 'admin', User.email.is_not(None))).all()
    notification = None
    if changed and current_signature:
        notification = email_service.send_system_alert(db, recipients=list(recipients), issues=snapshot['issues'])
    elif changed and previous_signature and not current_signature:
        notification = email_service.send_system_alert(db, recipients=list(recipients), issues=['Base de dados, portal, armazenamento e email operacionais.'], recovered=True)
    _set_setting(db, MONITOR_STATE_KEY, snapshot)
    _set_setting(db, MONITOR_RUN_KEY, {'checkedAt': snapshot['checkedAt'], 'ok': snapshot['ok'], 'notified': notification.status if notification else None})
    db.commit()
    logger.info('system_monitor ok=%s issues=%s notification=%s', snapshot['ok'], len(snapshot['issues']), notification.status if notification else 'unchanged')
    return snapshot
