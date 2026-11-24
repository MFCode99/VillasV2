from __future__ import annotations

import json
from pathlib import Path
import subprocess
from datetime import UTC, datetime
from typing import Any

from .config import get_settings


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(value, dict) or not str(value.get('version', '')).strip():
        return None
    notes = value.get('notes')
    value['notes'] = [str(note).strip() for note in notes if str(note).strip()] if isinstance(notes, list) else []
    sections = []
    for section in value.get('sections') or []:
        if not isinstance(section, dict):
            continue
        items = [str(item).strip() for item in section.get('items') or [] if str(item).strip()]
        if items:
            sections.append({'title': str(section.get('title') or 'Alterações').strip(), 'items': items})
    value['sections'] = sections
    value['title'] = str(value.get('title') or f"Versão {value['version']}").strip()
    value['summary'] = str(value.get('summary') or '').strip()
    value['channel'] = str(value.get('channel') or 'stable').strip().casefold()
    if value['channel'] not in {'stable', 'beta', 'experimental', 'test'}:
        value['channel'] = 'stable'
    value['notifyAdminsOnLogin'] = bool(value.get('notifyAdminsOnLogin', True))
    return value


def _history(update_dir: Path, current: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history_dir = update_dir / 'history'
    if history_dir.is_dir():
        for path in history_dir.glob('*.json'):
            manifest = _read_manifest(path)
            if manifest:
                rows.append(manifest)
    if current and not any(row['version'] == current['version'] for row in rows):
        rows.append(current)
    rows.sort(key=lambda row: (str(row.get('installedAt') or row.get('releasedAt') or ''), row['version']), reverse=True)
    return rows


def update_status() -> dict[str, Any]:
    update_dir = get_settings().update_dir
    current = _read_manifest(update_dir / 'current.json')
    pending = _read_manifest(update_dir / 'pending' / 'manifest.json')
    package_ready = (update_dir / 'pending' / 'payload.tar.gz').is_file()
    return {
        'current': current,
        'pending': pending,
        'history': _history(update_dir, current),
        'updateAvailable': bool(pending and package_ready),
        'state': 'ready' if pending and package_ready else ('incomplete' if pending else 'current'),
    }


def update_pending_metadata(*, channel: str, notify_admins_on_login: bool) -> dict[str, Any]:
    normalized_channel = str(channel or '').strip().casefold()
    if normalized_channel not in {'stable', 'beta', 'experimental', 'test'}:
        raise ValueError('invalid_update_channel')
    update_dir = get_settings().update_dir
    path = update_dir / 'pending' / 'manifest.json'
    manifest = _read_manifest(path)
    if manifest is None:
        raise FileNotFoundError('pending_update_not_found')
    manifest['channel'] = normalized_channel
    manifest['notifyAdminsOnLogin'] = bool(notify_admins_on_login)
    manifest['metadataUpdatedAt'] = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
    return manifest


def start_update() -> dict[str, Any]:
    status = update_status()
    if not status['updateAvailable']:
        return {**status, 'started': False}
    subprocess.Popen(
        ['sudo', '-n', '/usr/local/sbin/villas-v2-apply-update'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {**status, 'started': True}
