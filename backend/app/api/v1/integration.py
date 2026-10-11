"""Server-to-server ingestion for the booking app.

Authenticated with a shared API key (``X-API-Key``), not a user JWT. See
``app.services.ingestion_service`` for the create-or-return semantics.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_integration_key
from app.database import get_db
from app.schemas.integration import IngestOrderRequest, IngestOrderResponse
from app.services import ingestion_service

router = APIRouter(prefix="/integration", tags=["integration"])


@router.post(
    "/orders",
    response_model=IngestOrderResponse,
    dependencies=[Depends(require_integration_key)],
)
def ingest_order(
    data: IngestOrderRequest,
    db: Session = Depends(get_db),
) -> IngestOrderResponse:
    order, already_existed = ingestion_service.ingest_order(db, data)
    return IngestOrderResponse(
        order_id=order.id,
        status=order.status.value,
        external_order_ref=order.external_order_ref or data.external_order_ref,
        already_existed=already_existed,
    )
