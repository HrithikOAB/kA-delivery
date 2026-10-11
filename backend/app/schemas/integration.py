"""Schemas for the booking-app order ingestion endpoint.

The booking app owns its own catalogue, so items arrive as free-form snapshots
(name + price + qty) rather than references to this backend's ``MenuItem`` rows.
Totals are always recomputed here, server-side.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IngestMess(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address_text: str = Field(default="", max_length=255)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    contact_phone: str = Field(default="", max_length=32)


class IngestCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=32)


class IngestItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unit_price_cents: int = Field(ge=0)
    quantity: int = Field(ge=1, le=50)
    packaging_note: str = Field(default="", max_length=255)


class IngestDropoff(BaseModel):
    address_text: str = Field(min_length=1, max_length=255)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    note: str = Field(default="", max_length=512)


class IngestOrderRequest(BaseModel):
    external_order_ref: str = Field(min_length=1, max_length=128)
    mess: IngestMess
    customer: IngestCustomer
    items: list[IngestItem] = Field(min_length=1)
    dropoff: IngestDropoff
    payment_method: str = Field(default="cod", max_length=24)
    # Optional: booking app may pass its own delivery fee; otherwise 0.
    delivery_fee_cents: int = Field(default=0, ge=0)


class IngestOrderResponse(BaseModel):
    order_id: int
    status: str
    external_order_ref: str
    already_existed: bool = False
