"""Active delivery screen enrichment for rider map + drop-off UI."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.delivery import Delivery, DeliveryBatch
from app.models.enums import BatchStatus
from app.models.order import Order
from app.models.user import User

def _split_address(address_text: str) -> tuple[str, str]:
    parts = [p.strip() for p in address_text.split(",", 1)]
    if len(parts) == 2 and parts[1]:
        return parts[0], parts[1]
    return address_text, ""


def ensure_order_address(order: Order) -> None:
    """Split the stored address into title/subtitle. No fabricated tags or notes."""
    if order.address_title:
        return
    title, subtitle = _split_address(order.address_text)
    order.address_title = title
    order.address_subtitle = subtitle


def ensure_delivery_tracking(delivery: Delivery, order: Order) -> None:
    """Derive deliver-by only from a real ETA; never invent ETA/distance/route."""
    if (
        delivery.eta_minutes is None
        and delivery.estimated_minutes is not None
    ):
        delivery.eta_minutes = delivery.estimated_minutes
    if delivery.distance_remaining_km is None and delivery.distance_km is not None:
        delivery.distance_remaining_km = round(delivery.distance_km, 1)
    if delivery.deliver_by_at is None and delivery.eta_minutes is not None:
        delivery.deliver_by_at = utcnow() + timedelta(minutes=delivery.eta_minutes)
    if not order.customer_note and delivery.handover_instructions:
        order.customer_note = delivery.handover_instructions


def enrich_stop(order: Order, delivery: Delivery, customer: User | None) -> dict:
    ensure_order_address(order)
    ensure_delivery_tracking(delivery, order)
    deliver_by = delivery.deliver_by_at
    deliver_label = (
        deliver_by.strftime("%I:%M %p").lstrip("0").upper() if deliver_by else None
    )
    return {
        "address_title": order.address_title or order.address_text,
        "address_subtitle": order.address_subtitle,
        "address_tag": order.address_tag,
        "customer_note": order.customer_note,
        "customer_phone": (customer.phone or "") if customer else "",
        "customer_verified": order.customer_verified,
        "eta_minutes": delivery.eta_minutes,
        "distance_remaining_km": delivery.distance_remaining_km,
        "route_label": delivery.route_label or None,
        "deliver_by_label": f"BY {deliver_label}" if deliver_label else None,
        "arrived_at_drop": delivery.arrived_at_drop_at is not None,
        "helper_text": None,
    }


def build_active_meta(
    db: Session,
    batch: DeliveryBatch,
    rider_id: int,
    delivery: Delivery,
    order: Order,
) -> dict:
    rider = db.get(User, rider_id)
    profile = rider.rider_profile if rider else None
    ensure_delivery_tracking(delivery, order)
    phase = "delivering" if batch.status == BatchStatus.picked_up else "pickup"
    status_label = (
        "On the way to customer" if phase == "delivering" else "Heading to kitchen"
    )
    deliver_by = delivery.deliver_by_at
    deliver_label = (
        deliver_by.strftime("%I:%M %p").lstrip("0").upper() if deliver_by else "SOON"
    )
    return {
        "phase": phase,
        "status_label": status_label,
        "eta_minutes": delivery.eta_minutes,
        "distance_remaining_km": delivery.distance_remaining_km,
        "route_label": delivery.route_label or None,
        "deliver_by_label": f"BY {deliver_label}" if deliver_label else None,
        "rider_lat": profile.last_lat if profile else None,
        "rider_lng": profile.last_lng if profile else None,
        "arrived_at_drop": delivery.arrived_at_drop_at is not None,
        "helper_text": None,
    }


def mark_arrived_at_drop(delivery: Delivery) -> dict:
    if delivery.arrived_at_drop_at is None:
        delivery.arrived_at_drop_at = utcnow()
    return {"ok": True, "arrived": True, "arrived_at": delivery.arrived_at_drop_at.isoformat()}

