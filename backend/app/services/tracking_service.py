"""Tracking snapshot construction and per-order authorization."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.delivery import Delivery
from app.models.enums import TERMINAL_ORDER_STATUSES, OrderStatus, UserRole
from app.models.mess import Mess
from app.models.order import Order
from app.models.user import User
from app.schemas.tracking import RiderMarker, TrackingSnapshot
from app.services import location_service
from app.services.eta_service import estimate_eta_minutes, haversine_km

# Statuses at which the rider position is meaningful to the customer.
_RIDER_VISIBLE_STATUSES = {
    OrderStatus.assigned,
    OrderStatus.picked_up,
    OrderStatus.out_for_delivery,
}

_TIMELINE_ORDER = [
    OrderStatus.placed,
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.assigned,
    OrderStatus.picked_up,
    OrderStatus.out_for_delivery,
    OrderStatus.delivered,
]

_TIMELINE_LABELS = {
    OrderStatus.placed: "Order placed",
    OrderStatus.accepted: "Accepted by mess",
    OrderStatus.preparing: "Preparing your meal",
    OrderStatus.ready: "Ready for pickup",
    OrderStatus.assigned: "Rider assigned",
    OrderStatus.picked_up: "Picked up",
    OrderStatus.out_for_delivery: "Out for delivery",
    OrderStatus.delivered: "Delivered",
}


def customer_can_view(order: Order, user: User) -> bool:
    """Only the owning customer may view an order's live tracking."""
    return order.customer_id == user.id


def admin_can_view(order: Order, user: User) -> bool:
    """Admins may view any order's tracking (operations monitoring).

    Tracking stays order-scoped and reuses the same snapshot the customer sees;
    no second tracking system is introduced.
    """
    return user.has_role(UserRole.admin)


def build_snapshot(db: Session, order: Order) -> TrackingSnapshot:
    mess = db.get(Mess, order.mess_id) if order.mess_id is not None else None
    delivery = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()

    is_terminal = order.status in TERMINAL_ORDER_STATUSES
    is_trackable = not is_terminal

    rider_name = rider_phone = None
    rider_marker: RiderMarker | None = None
    eta_minutes = distance_km = None

    rider_reserved = delivery is not None and delivery.rider_id is not None
    rider_active = order.status in _RIDER_VISIBLE_STATUSES
    show_rider = rider_reserved and (
        rider_active
        or order.status in {OrderStatus.accepted, OrderStatus.preparing, OrderStatus.ready}
    )

    if is_trackable and show_rider:
        rider = db.get(User, delivery.rider_id)
        if rider is not None:
            rider_name = rider.full_name
            rider_phone = rider.phone
        loc = location_service.latest_location(db, delivery.rider_id)
        if loc is not None:
            now = utcnow()
            rider_marker = RiderMarker(
                lat=loc.lat,
                lng=loc.lng,
                heading=loc.heading,
                speed=loc.speed,
                server_timestamp=loc.server_timestamp,
                is_stale=location_service.is_stale(loc, now),
                age_seconds=location_service.age_seconds(loc, now),
            )
            # ETA from the rider's live position once the meal is en route,
            # otherwise from the mess to the customer.
            has_dropoff = order.address_lat is not None and order.address_lng is not None
            if has_dropoff and order.status == OrderStatus.out_for_delivery:
                distance_km = haversine_km(
                    loc.lat, loc.lng, order.address_lat, order.address_lng
                )
            elif has_dropoff and mess is not None:
                distance_km = haversine_km(
                    mess.lat, mess.lng, order.address_lat, order.address_lng
                )
            if distance_km is not None:
                eta_minutes = estimate_eta_minutes(distance_km)

    return TrackingSnapshot(
        order_id=order.id,
        status=order.status,
        is_trackable=is_trackable,
        updated_at=utcnow(),
        mess_name=mess.name if mess else None,
        mess_lat=mess.lat if mess else None,
        mess_lng=mess.lng if mess else None,
        dropoff_lat=order.address_lat,
        dropoff_lng=order.address_lng,
        dropoff_text=order.address_text,
        rider_name=rider_name,
        rider_phone=rider_phone,
        rider_location=rider_marker,
        eta_minutes=eta_minutes,
        distance_km=round(distance_km, 2) if distance_km is not None else None,
        timeline=_build_timeline(order.status),
    )


def _build_timeline(current: OrderStatus) -> list[dict]:
    if current == OrderStatus.cancelled:
        return [{"status": "cancelled", "label": "Order cancelled", "state": "current"}]
    try:
        current_idx = _TIMELINE_ORDER.index(current)
    except ValueError:
        current_idx = -1
    steps = []
    for idx, status in enumerate(_TIMELINE_ORDER):
        if idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "current"
        else:
            state = "pending"
        steps.append(
            {"status": status.value, "label": _TIMELINE_LABELS[status], "state": state}
        )
    return steps
