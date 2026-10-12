"""Response shape of the external ``getRiderOrder`` API.

Fields are lenient (defaults / nullable) because the upstream fills unknown
values with ``null`` or empty strings rather than omitting them.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExternalLocation(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class ExternalCustomer(BaseModel):
    customer_id: str | None = None
    name: str = ""
    location: ExternalLocation = Field(default_factory=ExternalLocation)
    contact_number: str | None = None
    address: str = ""
    instruction: str = ""


class ExternalMess(BaseModel):
    mess_id: str | None = None
    name: str = ""
    location: ExternalLocation = Field(default_factory=ExternalLocation)
    contact_number: str | None = None
    address: str = ""


class ExternalOrderItem(BaseModel):
    item_id: str | None = None
    name: str = ""
    quantity: int = 1
    price: float = 0
    food_type: str | None = None


class ExternalOrderDetails(BaseModel):
    order_id: str
    order_items: list[ExternalOrderItem] = Field(default_factory=list)
    payment_method: str | None = None
    payment_status: str | None = None
    order_status: str | None = None
    delivery_partner_commission: float = 0
    currency: str = "INR"
    placed_at: str | None = None
    order_type: str | None = None
    # Amounts are in rupees (major units).
    item_total: float = 0
    delivery_charge: float = 0
    grand_total: float = 0
    amount_to_collect: float = 0
    partner_order_id: str | None = None


class ExternalOrder(BaseModel):
    customer_details: ExternalCustomer
    mess_details: ExternalMess
    order_details: ExternalOrderDetails


def to_cents(amount: float) -> int:
    return int(round(amount * 100))
