"""Issue, rotate, revoke and verify partner API keys.

Keys look like ``kd_live_<43 url-safe chars>``. Only a SHA-256 hash is stored,
so a key can be shown exactly once (on create/rotate) and never recovered.
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.partner_api_key import PartnerApiKey
from app.models.user import User
from app.services import audit_service

KEY_PREFIX = "kd_live_"
_DISPLAY_PREFIX_LEN = len(KEY_PREFIX) + 4


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_raw_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def _set_key(row: PartnerApiKey) -> str:
    raw = _new_raw_key()
    row.key_hash = hash_key(raw)
    row.key_prefix = raw[:_DISPLAY_PREFIX_LEN]
    return raw


def list_keys(db: Session) -> list[PartnerApiKey]:
    return list(
        db.execute(select(PartnerApiKey).order_by(PartnerApiKey.id.desc())).scalars().all()
    )


def _get(db: Session, key_id: int) -> PartnerApiKey:
    row = db.get(PartnerApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return row


def create_key(db: Session, admin: User, name: str) -> tuple[PartnerApiKey, str]:
    row = PartnerApiKey(name=name.strip(), is_active=True, created_by_user_id=admin.id)
    raw = _set_key(row)
    db.add(row)
    db.flush()
    audit_service.record(
        db, actor_user_id=admin.id, action="partner_api_key_created",
        target_type="partner_api_key", target_id=row.id, detail=row.name,
    )
    db.commit()
    db.refresh(row)
    return row, raw


def rotate_key(db: Session, admin: User, key_id: int) -> tuple[PartnerApiKey, str]:
    """Replace the secret; the old key stops working immediately."""
    row = _get(db, key_id)
    if not row.is_active:
        raise HTTPException(status_code=409, detail="Revoked keys cannot be rotated")
    raw = _set_key(row)
    row.rotated_at = utcnow()
    row.last_used_at = None
    audit_service.record(
        db, actor_user_id=admin.id, action="partner_api_key_rotated",
        target_type="partner_api_key", target_id=row.id, detail=row.name,
    )
    db.commit()
    db.refresh(row)
    return row, raw


def revoke_key(db: Session, admin: User, key_id: int) -> PartnerApiKey:
    row = _get(db, key_id)
    if row.is_active:
        row.is_active = False
        row.revoked_at = utcnow()
        audit_service.record(
            db, actor_user_id=admin.id, action="partner_api_key_revoked",
            target_type="partner_api_key", target_id=row.id, detail=row.name,
        )
        db.commit()
        db.refresh(row)
    return row


def has_active_keys(db: Session) -> bool:
    return db.execute(
        select(PartnerApiKey.id).where(PartnerApiKey.is_active.is_(True)).limit(1)
    ).first() is not None


def verify(db: Session, raw: str) -> PartnerApiKey | None:
    """Return the active key matching ``raw`` (and stamp its last use), else None."""
    row = db.execute(
        select(PartnerApiKey).where(
            PartnerApiKey.key_hash == hash_key(raw),
            PartnerApiKey.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is not None:
        row.last_used_at = utcnow()
        db.commit()
    return row
