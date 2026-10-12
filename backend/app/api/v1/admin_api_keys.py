"""Super-admin management of partner API keys (``X-API-Key`` for /api/v1/partner)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin_permission
from app.database import get_db
from app.models.partner_api_key import PartnerApiKey
from app.models.user import User
from app.schemas.partner_api import (
    PartnerApiKeyCreate,
    PartnerApiKeyOut,
    PartnerApiKeySecretOut,
)
from app.services import partner_key_service

router = APIRouter(prefix="/admin/api-keys", tags=["admin"])

# No tiers listed: only super_admin may issue or change partner credentials.
_super_admin = require_admin_permission()


def _secret_out(row: PartnerApiKey, raw: str) -> PartnerApiKeySecretOut:
    return PartnerApiKeySecretOut(
        **PartnerApiKeyOut.model_validate(row).model_dump(), api_key=raw
    )


@router.get("", response_model=list[PartnerApiKeyOut])
def list_api_keys(
    _: User = Depends(_super_admin), db: Session = Depends(get_db)
) -> list[PartnerApiKeyOut]:
    return [PartnerApiKeyOut.model_validate(k) for k in partner_key_service.list_keys(db)]


@router.post("", response_model=PartnerApiKeySecretOut, status_code=status.HTTP_201_CREATED)
def create_api_key(
    data: PartnerApiKeyCreate,
    admin: User = Depends(_super_admin),
    db: Session = Depends(get_db),
) -> PartnerApiKeySecretOut:
    row, raw = partner_key_service.create_key(db, admin, data.name)
    return _secret_out(row, raw)


@router.post("/{key_id}/rotate", response_model=PartnerApiKeySecretOut)
def rotate_api_key(
    key_id: int, admin: User = Depends(_super_admin), db: Session = Depends(get_db)
) -> PartnerApiKeySecretOut:
    row, raw = partner_key_service.rotate_key(db, admin, key_id)
    return _secret_out(row, raw)


@router.post("/{key_id}/revoke", response_model=PartnerApiKeyOut)
def revoke_api_key(
    key_id: int, admin: User = Depends(_super_admin), db: Session = Depends(get_db)
) -> PartnerApiKeyOut:
    return PartnerApiKeyOut.model_validate(partner_key_service.revoke_key(db, admin, key_id))
