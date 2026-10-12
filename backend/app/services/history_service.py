"""Rider delivery history with filters and summary stats."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.delivery import Delivery
from app.models.enums import DeliveryStatus, OrderStatus
from app.models.mess import Mess
from app.models.order import Order
from app.services.eta_service import haversine_km
from app.services.pricing_service import surge_cents_for_order

PERIOD_LABELS = {
    "today": "Today",
    "yesterday": "Yesterday",
    "this_week": "This Week",
    "this_month": "This Month",
    "all": "All Time",
}


def _period_bounds(period: str, now: datetime | None = None) -> tuple[datetime | None, datetime | None, str]:
    now = now or datetime.utcnow()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, f"Today ({now.strftime('%b %d')})"
    if period == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        return start, end, f"Yesterday ({start.strftime('%b %d')})"
    if period == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=6)
        return start, end + timedelta(days=1), f"This Week ({start.strftime('%b %d')} - {end.strftime('%b %d')})"
    if period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now, f"This Month ({now.strftime('%B %Y')})"
    return None, None, PERIOD_LABELS.get(period, "All Time")


def _area_from_address(address: str) -> str:
    if not address:
        return "Delivery zone"
    parts = [p.strip() for p in address.replace("\n", ",").split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[-2]
    if len(parts) >= 2:
        return parts[-2] if len(parts[-1]) < 12 else parts[-1]
    return parts[0][:48]


def _time_label(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "—"
    now = now or datetime.utcnow()
    day = dt.date()
    today = now.date()
    time_part = dt.strftime("%I:%M %p").lstrip("0")
    if day == today:
        prefix = "Today"
    elif day == today - timedelta(days=1):
        prefix = "Yesterday"
    else:
        prefix = dt.strftime("%b %d")
    return f"{prefix}, {time_part}"


def _distance_for(delivery: Delivery, order: Order, mess: Mess | None) -> float | None:
    if delivery.distance_km is not None:
        return round(delivery.distance_km, 1)
    if mess and order and order.address_lat is not None and order.address_lng is not None:
        return round(haversine_km(mess.lat, mess.lng, order.address_lat, order.address_lng), 1)
    return None


def _ticket_ref(order_id: int) -> str:
    return f"#DM-{8800 + order_id}"


def capture_delivery_metrics(delivery: Delivery, order: Order, mess: Mess | None) -> None:
    """Persist distance/surge/tip when a delivery completes."""
    dist = _distance_for(delivery, order, mess)
    if dist is not None:
        delivery.distance_km = dist
    surge = surge_cents_for_order(order)
    base = max(delivery.earning_cents - surge, 1500)
    if surge > 0 and base > 0:
        delivery.surge_multiplier = round(1 + surge / base, 1)
    elif delivery.surge_multiplier < 1.0:
        delivery.surge_multiplier = 1.0
    if delivery.picked_up_at and delivery.delivered_at:
        delta = delivery.delivered_at - delivery.picked_up_at
        delivery.active_minutes = max(1, int(delta.total_seconds() // 60))
def build_history(
    db: Session,
    rider_id: int,
    status: str = "completed",
    period: str = "this_week",
) -> dict:
    now = datetime.utcnow()
    start, end, period_label = _period_bounds(period, now)

    completed_q = select(Delivery).where(
        Delivery.rider_id == rider_id,
        Delivery.status == DeliveryStatus.delivered,
    )
    cancelled_q = select(Delivery).where(
        Delivery.rider_id == rider_id,
        Delivery.status == DeliveryStatus.cancelled,
    )

    if start:
        completed_q = completed_q.where(Delivery.delivered_at >= start)
        cancelled_q = cancelled_q.where(Delivery.updated_at >= start)
    if end:
        completed_q = completed_q.where(Delivery.delivered_at < end)
        cancelled_q = cancelled_q.where(Delivery.updated_at < end)

    completed_all = db.execute(completed_q).scalars().all()
    cancelled_all = db.execute(cancelled_q).scalars().all()

    # Also count order-cancelled where rider was assigned
    if start or end:
        order_cancelled = []
    else:
        order_cancelled = []

    completed_count = len(completed_all)
    cancelled_count = len(cancelled_all)
    total_earned = sum(d.earning_cents + d.tip_cents for d in completed_all)

    pool = completed_all if status == "completed" else cancelled_all
    pool = sorted(pool, key=lambda d: (d.delivered_at or d.updated_at or now), reverse=True)

    items = []
    for d in pool:
        order = db.get(Order, d.order_id)
        mess = db.get(Mess, order.mess_id) if order else None
        is_completed = d.status == DeliveryStatus.delivered
        items.append({
            "delivery_id": d.id,
            "order_id": d.order_id,
            "ticket_ref": _ticket_ref(d.order_id),
            "status": "completed" if is_completed else "cancelled",
            "status_label": "COMPLETED" if is_completed else "CANCELLED",
            "mess_name": mess.name if mess else "Kitchen",
            "dropoff_area": _area_from_address(order.address_text if order else ""),
            "completed_at": d.delivered_at if is_completed else d.updated_at,
            "time_label": _time_label(d.delivered_at if is_completed else d.updated_at, now),
            "distance_km": _distance_for(d, order, mess) if order else None,
            "amount_cents": d.earning_cents if is_completed else 0,
            "tip_cents": d.tip_cents if is_completed else 0,
            "surge_multiplier": d.surge_multiplier if d.surge_multiplier > 1.0 else None,
            "has_surge": bool(d.surge_multiplier and d.surge_multiplier > 1.0),
        })

    return {
        "period": period,
        "period_label": period_label,
        "status": status,
        "summary": {
            "completed_count": completed_count,
            "cancelled_count": cancelled_count,
            "total_earned_cents": total_earned,
        },
        "items": items,
    }
