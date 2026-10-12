"""Offer detail for the delivery offer screen."""
from __future__ import annotations

from app.models.delivery import DeliveryBatch, DeliveryOffer
from app.models.enums import PaymentStatus
from app.models.mess import Mess
from app.models.order import Order
from app.services import pricing_service
from app.services.eta_service import estimate_eta_minutes, haversine_km


def _item_tags(order: Order) -> list[str]:
    return [f"{item.quantity}× {item.name_snapshot}" for item in order.items][:4]


def _is_prepaid(order: Order) -> bool:
    return order.payment_status == PaymentStatus.paid or order.payment_method != "cod"


def build_offer_detail(
    offer: DeliveryOffer,
    batch: DeliveryBatch,
    mess: Mess | None,
    orders: list[Order],
    stops: list,
    earnings: dict,
    rider_lat: float | None = None,
    rider_lng: float | None = None,
) -> dict:
    first = orders[0] if orders else None

    pickup_km = (
        round(haversine_km(rider_lat, rider_lng, mess.lat, mess.lng), 1)
        if mess is not None and rider_lat is not None and rider_lng is not None
        else None
    )
    drop_km = pricing_service.route_km(first, mess) if first else None
    known = [d for d in (pickup_km, drop_km) if d is not None]
    total_km = round(sum(known), 1) if known else None
    est_mins = int(estimate_eta_minutes(total_km)) if total_km is not None else None

    pays = [pricing_service.delivery_pay(o, mess) for o in orders]
    distance_pay = sum(p["distance_pay_cents"] for p in pays)
    base_fare = sum(p["base_fare_cents"] for p in pays)
    surge = earnings["surge_cents"]
    item_count = sum(i.quantity for o in orders for i in o.items)
    prepaid = _is_prepaid(first) if first else False

    return {
        "id": offer.id,
        "batch_id": offer.batch_id,
        "status": offer.status,
        "sent_at": offer.sent_at,
        "expires_at": offer.expires_at,
        "mess_name": mess.name if mess else None,
        "mess_lat": mess.lat if mess else None,
        "mess_lng": mess.lng if mess else None,
        "mess_address": mess.address_text if mess else "",
        "order_count": len(orders),
        "base_earning_cents": earnings["base_earning_cents"],
        "surge_cents": surge,
        "estimated_earning_cents": earnings["estimated_earning_cents"],
        "stops": stops,
        "total_distance_km": total_km,
        "estimated_minutes": est_mins,
        "pickup_distance_km": pickup_km,
        "drop_distance_km": drop_km,
        "payout": {
            "base_fare_cents": base_fare,
            "base_fare_label": "Base fare",
            "distance_pay_cents": distance_pay,
            "distance_label": f"{drop_km} km to drop-off" if drop_km is not None else "Distance unknown",
            "surge_bonus_cents": surge,
            "surge_label": "Peak-hour bonus" if surge else None,
            "tip_cents": 0,
            "total_cents": earnings["estimated_earning_cents"],
        },
        "order_summary": {
            "item_count": item_count,
            "item_tags": _item_tags(first) if first else [],
            "payment_label": "Prepaid" if prepaid else "Cash on delivery",
            "is_prepaid": prepaid,
        },
    }
