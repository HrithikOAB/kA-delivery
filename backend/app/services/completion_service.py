"""Delivery completion summary for the partner success screen."""
from __future__ import annotations

from app.models.delivery import Delivery
from app.models.mess import Mess
from app.models.order import Order
from app.models.user import User
from app.services.eta_service import haversine_km
from app.services.order_labels import area_from_address, order_ref
from app.services.pricing_service import surge_cents_for_order

BASE_FARE_CENTS = 9000
DISTANCE_RATE_CENTS_PER_KM = 833  # ~₹8.33/km


def _distance_km(delivery: Delivery, order: Order, mess: Mess | None) -> float | None:
    if delivery.distance_km is not None:
        return delivery.distance_km
    if mess and order.address_lat is not None and order.address_lng is not None:
        return round(haversine_km(mess.lat, mess.lng, order.address_lat, order.address_lng), 1)
    return None


def capture_completion_metrics(
    delivery: Delivery,
    order: Order,
    mess: Mess | None,
    customer: User | None = None,
) -> None:
    """Persist payout breakdown, timing and rating when a delivery completes."""
    dist = _distance_km(delivery, order, mess)
    if dist is not None:
        delivery.distance_km = dist

    surge = surge_cents_for_order(order)
    distance_pay = int((dist or 0) * DISTANCE_RATE_CENTS_PER_KM)
    delivery.base_fare_cents = BASE_FARE_CENTS
    delivery.distance_pay_cents = distance_pay
    delivery.surge_bonus_cents = surge
    delivery.earning_cents = BASE_FARE_CENTS + distance_pay + surge

    if surge > 0 and delivery.earning_cents > surge:
        base = delivery.earning_cents - surge
        delivery.surge_multiplier = round(1 + surge / base, 1) if base > 0 else 1.0

    delivery.estimated_minutes = max(15, int(12 + (dist or 0) * 3.5))
    if delivery.picked_up_at and delivery.delivered_at:
        delta = delivery.delivered_at - delivery.picked_up_at
        delivery.active_minutes = max(1, int(delta.total_seconds() // 60))
    elif not delivery.active_minutes:
        delivery.active_minutes = delivery.estimated_minutes


def build_completion_summary(
    delivery: Delivery,
    order: Order,
    mess: Mess | None,
    customer: User | None = None,
) -> dict:
    dist = delivery.distance_km if delivery.distance_km is not None else _distance_km(delivery, order, mess)
    dist_val = dist or 0.0
    active = delivery.active_minutes or 18
    estimated = delivery.estimated_minutes or max(15, int(12 + dist_val * 3.5))
    faster = max(0, estimated - active)
    total = delivery.earning_cents + delivery.tip_cents
    customer_name = customer.full_name if customer else "Customer"
    first_name = customer_name.split()[0] if customer_name else "Customer"
    surge_label = f"{delivery.surge_multiplier}x" if delivery.surge_multiplier > 1.0 else None
    hub = area_from_address(order.address_text)

    return {
        "delivery_id": delivery.id,
        "order_id": order.id,
        "ticket_ref": order_ref(order),
        "status": delivery.status.value,
        "status_label": "Delivered",
        "mess_name": mess.name if mess else "Kitchen",
        "mess_verified": bool(mess),
        "dropoff_area": hub,
        "address_text": order.address_text,
        "customer_name": customer_name,
        "total_earned_cents": total,
        "wallet_credited": True,
        "active_minutes": active,
        "estimated_minutes": estimated,
        "minutes_faster": faster,
        "rider_rating": delivery.rider_rating,
        "rating_comment": delivery.rating_comment,
        "distance_km": dist,
        "payout": {
            "base_fare_cents": delivery.base_fare_cents or BASE_FARE_CENTS,
            "base_fare_label": "Fixed pickup & drop rate",
            "distance_pay_cents": delivery.distance_pay_cents,
            "distance_label": f"{dist_val} km" if dist is not None else "Distance n/a",
            "surge_bonus_cents": delivery.surge_bonus_cents,
            "surge_multiplier": delivery.surge_multiplier if delivery.surge_multiplier > 1.0 else None,
            "surge_label": surge_label,
            "surge_zone": f"{hub} lunch demand" if delivery.surge_bonus_cents > 0 else None,
            "tip_cents": delivery.tip_cents,
            "tip_customer": first_name,
            "total_cents": total,
        },
        "pending_stops": 0,
        "route_timeline": [
            {"kind": "pickup", "title": mess.name if mess else "Kitchen", "subtitle": mess.address_text if mess else ""},
            {"kind": "drop", "title": order.address_title or order.address_text, "subtitle": order.address_subtitle or order.address_text},
        ],
    }
