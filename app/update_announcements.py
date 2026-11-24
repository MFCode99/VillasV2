from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from .models import UpdateAnnouncement, UpdateAnnouncementReceipt, User
from .security import utcnow
from .update_manager import update_status


def _releases() -> list[dict[str, Any]]:
    status = update_status()
    values = [status.get('pending'), status.get('current'), *(status.get('history') or [])]
    releases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for release in values:
        version = str((release or {}).get('version') or '').strip()
        if not version or version in seen:
            continue
        seen.add(version)
        releases.append(release)
    return releases


def available_releases() -> list[dict[str, Any]]:
    result = []
    for release in _releases():
        sections = release.get('sections') or ([{'title': 'Alterações', 'items': release.get('notes') or []}] if release.get('notes') else [])
        result.append({
            'version': release['version'],
            'title': release.get('title') or f"Versão {release['version']}",
            'summary': release.get('summary') or '',
            'channel': release.get('channel') or 'stable',
            'releasedAt': release.get('installedAt') or release.get('releasedAt'),
            'sections': sections,
        })
    return result


def _release(version: str) -> dict[str, Any] | None:
    return next((release for release in available_releases() if release['version'] == version), None)


def create_announcement(db: Session, *, version: str, selected_notes: list[str], created_by_user_id: int) -> UpdateAnnouncement:
    release = _release(version)
    if release is None:
        raise LookupError('update_release_not_found')
    note_locations: dict[str, str] = {}
    for section in release['sections']:
        for note in section.get('items') or []:
            note_locations[str(note)] = str(section.get('title') or 'Alterações')
    unique_notes = list(dict.fromkeys(str(note).strip() for note in selected_notes if str(note).strip()))
    if not unique_notes or any(note not in note_locations for note in unique_notes):
        raise ValueError('update_announcement_notes_invalid')
    row = UpdateAnnouncement(
        version=release['version'],
        title=release['title'],
        summary=release['summary'],
        channel=release['channel'],
        selected_notes_json=[{'section': note_locations[note], 'text': note} for note in unique_notes],
        active=True,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_announcement_active(db: Session, announcement_id: int, active: bool) -> UpdateAnnouncement:
    row = db.get(UpdateAnnouncement, announcement_id)
    if row is None:
        raise LookupError('update_announcement_not_found')
    row.active = bool(active)
    db.commit()
    db.refresh(row)
    return row


def delete_announcement(db: Session, announcement_id: int) -> None:
    row = db.get(UpdateAnnouncement, announcement_id)
    if row is None:
        raise LookupError('update_announcement_not_found')
    db.delete(row)
    db.commit()


def _announcement_query():
    return select(UpdateAnnouncement).options(
        selectinload(UpdateAnnouncement.created_by_user),
        selectinload(UpdateAnnouncement.receipts).selectinload(UpdateAnnouncementReceipt.user),
    )


def _public(row: UpdateAnnouncement) -> dict[str, Any]:
    return {
        'id': row.id,
        'version': row.version,
        'title': row.title,
        'summary': row.summary or '',
        'channel': row.channel,
        'notes': list(row.selected_notes_json or []),
        'active': bool(row.active),
        'createdAt': row.created_at,
    }


def serialize_for_developer(row: UpdateAnnouncement, admins: list[User]) -> dict[str, Any]:
    receipts = {receipt.user_id: receipt for receipt in row.receipts}
    recipients = []
    for admin in admins:
        receipt = receipts.get(admin.id)
        recipients.append({
            'id': admin.id,
            'fullName': admin.full_name,
            'username': admin.username,
            'viewedAt': receipt.viewed_at if receipt else None,
            'acknowledgedAt': receipt.acknowledged_at if receipt else None,
            'ignoredAt': receipt.ignored_at if receipt else None,
            'status': 'acknowledged' if receipt and receipt.acknowledged_at else 'ignored' if receipt and receipt.ignored_at else 'viewed' if receipt else 'pending',
        })
    viewed = sum(item['status'] != 'pending' for item in recipients)
    acknowledged = sum(item['status'] == 'acknowledged' for item in recipients)
    ignored = sum(item['status'] == 'ignored' for item in recipients)
    return {
        **_public(row),
        'createdBy': row.created_by_user.full_name if row.created_by_user else '',
        'recipientCount': len(recipients),
        'viewedCount': viewed,
        'acknowledgedCount': acknowledged,
        'ignoredCount': ignored,
        'pendingCount': len(recipients) - viewed,
        'recipients': recipients,
    }


def developer_center(db: Session) -> dict[str, Any]:
    announcements = db.scalars(_announcement_query().order_by(desc(UpdateAnnouncement.created_at), desc(UpdateAnnouncement.id))).all()
    admins = db.scalars(select(User).where(User.role == 'admin', User.active.is_(True)).order_by(User.full_name)).all()
    return {
        'releases': available_releases(),
        'announcements': [serialize_for_developer(row, list(admins)) for row in announcements],
    }


def next_for_admin(db: Session, user_id: int) -> dict[str, Any] | None:
    row = db.scalar(
        _announcement_query()
        .where(
            UpdateAnnouncement.active.is_(True),
            ~UpdateAnnouncement.receipts.any(UpdateAnnouncementReceipt.user_id == user_id),
        )
        .order_by(desc(UpdateAnnouncement.created_at), desc(UpdateAnnouncement.id))
    )
    return _public(row) if row else None


def mark_viewed(db: Session, announcement_id: int, user_id: int, *, action: str | None = None) -> UpdateAnnouncementReceipt:
    announcement = db.get(UpdateAnnouncement, announcement_id)
    if announcement is None:
        raise LookupError('update_announcement_not_found')
    receipt = db.scalar(select(UpdateAnnouncementReceipt).where(
        UpdateAnnouncementReceipt.announcement_id == announcement_id,
        UpdateAnnouncementReceipt.user_id == user_id,
    ))
    now = utcnow()
    if receipt is None:
        receipt = UpdateAnnouncementReceipt(announcement_id=announcement_id, user_id=user_id, viewed_at=now)
        db.add(receipt)
    if action == 'acknowledged':
        receipt.acknowledged_at = now
        receipt.ignored_at = None
    elif action == 'ignored':
        receipt.ignored_at = now
        receipt.acknowledged_at = None
    db.commit()
    db.refresh(receipt)
    return receipt
