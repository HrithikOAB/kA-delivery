"""Display helpers shared by rider and admin screens."""
from __future__ import annotations

from app.models.order import Order


def order_ref(order: Order | None, order_id: int | None = None) -> str:
    """The external platform's order id when known, else our internal id."""
    if order is not None and order.external_order_ref:
        return order.external_order_ref
    return f"#{order.id if order is not None else order_id}"


def area_from_address(address: str | None) -> str:
    """Best-effort locality from a free-form address ("" when unknown)."""
    parts = [p.strip() for p in (address or "").replace("\n", ",").split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0][:48] if parts else ""
