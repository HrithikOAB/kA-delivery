"""Schemas for the external-partner API (``/api/v1/partner``)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartnerOrderRef(BaseModel):
    """Accepts ``{"order_id": "ORD-10001"}`` or ``{"orderId": 10001}``."""

    order_id: str | int | None = None
    orderId: str | int | None = None

    @model_validator(mode="after")
    def _one_id(self) -> "PartnerOrderRef":
        if self.order_id in (None, "") and self.orderId in (None, ""):
            raise ValueError("order_id (or orderId) is required")
        return self

    @property
    def raw(self) -> str | int:
        return self.order_id if self.order_id not in (None, "") else self.orderId  # type: ignore[return-value]


class PartnerOrderOut(BaseModel):
    order_id: str
    internal_id: int
    status: str
    created_at: datetime
    already_existed: bool = False


class PartnerApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class PartnerApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


class PartnerApiKeySecretOut(PartnerApiKeyOut):
    """Returned only by create/rotate: ``api_key`` is never retrievable again."""

    api_key: str


class PartnerDeliveryPartner(BaseModel):
    name: str
    phone: str | None = None
    vehicle_type: str | None = None
    vehicle_number: str | None = None
    rating: float | None = None


class PartnerLocation(BaseModel):
    lat: float
    lng: float
    heading: float | None = None
    speed: float | None = None
    updated_at: datetime
    is_stale: bool
    age_seconds: float


class PartnerTrackingOut(BaseModel):
    order_id: str
    status: str
    delivery_status: str | None = None
    updated_at: datetime
    delivery_partner: PartnerDeliveryPartner | None = None
    location: PartnerLocation | None = None
    eta_minutes: float | None = None
    distance_km: float | None = None
