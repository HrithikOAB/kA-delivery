"""Rider pay rule, shared by offer estimates and completion payouts.

Pay = base fare + per-km distance pay (mess -> drop-off) + peak-hour surge.
"""
from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.models.mess import Mess
from app.models.order import Order
from app.services.eta_service import haversine_km


def surge_cents_for_order(order: Order, now: datetime | None = None) -> int:
    """Peak-hour bonus: a share of the order's delivery fee at lunch/dinner."""
    hour = (now or datetime.utcnow()).hour
    fee = order.delivery_fee_cents
    if 12 <= hour < 14 or 19 <= hour < 22:
        return int(fee * 0.25)
    if 11 <= hour < 12 or 18 <= hour < 19:
        return int(fee * 0.15)
    return 0


def route_km(order: Order, mess: Mess | None) -> float | None:
    """Straight-line mess -> drop-off distance, or None without coordinates."""
    if mess is None or order.address_lat is None or order.address_lng is None:
        return None
    return round(haversine_km(mess.lat, mess.lng, order.address_lat, order.address_lng), 1)


def delivery_pay(order: Order, mess: Mess | None, distance_km: float | None = None) -> dict:
    dist = distance_km if distance_km is not None else route_km(order, mess)
    base = settings.rider_base_fare_cents
    distance_pay = int((dist or 0) * settings.rider_per_km_cents)
    surge = surge_cents_for_order(order)
    return {
        "base_fare_cents": base,
        "distance_km": dist,
        "distance_pay_cents": distance_pay,
        "surge_cents": surge,
        "total_cents": base + distance_pay + surge,
    }


def offer_earnings(orders: list[Order], mess: Mess | None) -> dict[str, int]:
    pays = [delivery_pay(o, mess) for o in orders]
    base = sum(p["base_fare_cents"] + p["distance_pay_cents"] for p in pays)
    surge = sum(p["surge_cents"] for p in pays)
    return {
        "base_earning_cents": base,
        "surge_cents": surge,
        "estimated_earning_cents": base + surge,
    }
