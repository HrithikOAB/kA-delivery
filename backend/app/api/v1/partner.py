"""Server-to-server API for external partners.

Authenticated with a shared API key (``X-API-Key``), not a user JWT.
- ``POST /partner/orders``: register an external order id (idempotent).
- ``POST /partner/tracking``: delivery status, partner details and live location.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_integration_key
from app.database import get_db
from app.schemas.partner_api import PartnerOrderOut, PartnerOrderRef, PartnerTrackingOut
from app.services import partner_order_service

router = APIRouter(
    prefix="/partner",
    tags=["partner"],
    dependencies=[Depends(require_integration_key)],
)


@router.post("/orders", response_model=PartnerOrderOut, status_code=status.HTTP_201_CREATED)
def register_order(
    data: PartnerOrderRef,
    response: Response,
    db: Session = Depends(get_db),
) -> PartnerOrderOut:
    out = partner_order_service.register_order(db, data.raw)
    if out.already_existed:
        response.status_code = status.HTTP_200_OK
    return out


@router.post("/tracking", response_model=PartnerTrackingOut)
def track_order(data: PartnerOrderRef, db: Session = Depends(get_db)) -> PartnerTrackingOut:
    return partner_order_service.tracking(db, data.raw)
