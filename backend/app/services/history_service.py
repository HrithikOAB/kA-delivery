"""Rider delivery history with filters and summary stats."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    if mess and order:
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
    # Demo tip: 10% chance style — use order total mod for stable demo
    if order.total_cents % 3 == 0:
        delivery.tip_cents = max(2000, int(order.total_cents * 0.05))


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


def seed_demo_history(db: Session, rider_id: int, customer_id: int, default_mess_id: int) -> None:
    """Populate demo delivery history for the partner app screens."""
    from sqlalchemy import select

    from app.models.delivery import Delivery, DeliveryBatch
    from app.models.enums import BatchStatus, DeliveryStatus, OrderStatus, PaymentStatus, PayoutStatus
    from app.models.mess import Mess
    from app.models.order import Order

    marker = db.execute(
        select(Delivery).where(Delivery.rider_id == rider_id, Delivery.order_id == 42)
    ).scalar_one_or_none()
    if marker:
        return

    default_mess = db.get(Mess, default_mess_id)
    if default_mess is None:
        return

    def _mess_id(name: str) -> int:
        if name == default_mess.name:
            return default_mess.id
        existing = db.execute(select(Mess).where(Mess.name == name)).scalar_one_or_none()
        if existing:
            return existing.id
        m = Mess(
            owner_user_id=default_mess.owner_user_id,
            name=name,
            description="Demo mess for history",
            address_text="Bengaluru",
            lat=default_mess.lat,
            lng=default_mess.lng,
            is_open=True,
            delivery_fee_cents=2000,
        )
        db.add(m)
        db.flush()
        return m.id

    now = datetime.utcnow()
    demos = [
        (42, "Annapoorna Tiffin & South Mess", "Bellandur Tech Zone", 4.8, 18500, 2000, 1.4, 0),
        (43, "Khana Delivery Kitchen", "HSR Layout Sector 2", 3.2, 17200, 0, 1.0, 1),
        (44, "Annapoorna Tiffin & South Mess", "Koramangala 5th Block", 5.1, 19800, 1500, 1.25, 2),
        (45, "South Spice Mess", "Bellandur Tech Zone", 2.4, 15600, 0, 1.0, 3),
        (46, "Khana Delivery Kitchen", "Indiranagar 100ft Road", 6.2, 21400, 2500, 1.5, 4),
        (47, "Annapoorna Tiffin & South Mess", "Marathahalli Bridge", 4.0, 18100, 0, 1.2, 5),
        (48, "South Spice Mess", "HSR Layout Sector 7", 3.6, 16900, 1000, 1.0, 6),
    ]
    cancelled = (49, "Khana Delivery Kitchen", "Whitefield ITPL", 3.0, 0, 0, 1.0, 7)

    def _add(order_id, mess_name, area, dist, earn, tip, surge, days_ago, cancelled=False):
        mid = _mess_id(mess_name)
        delivered = now - timedelta(days=days_ago, hours=days_ago % 5 + 2)
        order = Order(
            id=order_id,
            customer_id=customer_id,
            mess_id=mid,
            status=OrderStatus.cancelled if cancelled else OrderStatus.delivered,
            is_test=True,
            test_note="demo-history",
            address_text=f"Flat 12, {area}, Bengaluru",
            address_lat=12.9352 + days_ago * 0.002,
            address_lng=77.6245 + days_ago * 0.001,
            subtotal_cents=12000,
            delivery_fee_cents=2000,
            tax_cents=0,
            total_cents=14000,
            payment_status=PaymentStatus.paid,
            payment_method="cod",
            placed_at=delivered - timedelta(minutes=45),
            delivered_at=delivered if not cancelled else None,
        )
        db.add(order)
        db.flush()
        batch = DeliveryBatch(
            mess_id=mid,
            rider_id=rider_id,
            status=BatchStatus.completed if not cancelled else BatchStatus.cancelled,
            picked_up_at=delivered - timedelta(minutes=20),
            completed_at=delivered if not cancelled else None,
            total_earning_cents=earn,
        )
        db.add(batch)
        db.flush()
        delivery = Delivery(
            order_id=order.id,
            batch_id=batch.id,
            rider_id=rider_id,
            status=DeliveryStatus.cancelled if cancelled else DeliveryStatus.delivered,
            sequence=0,
            picked_up_at=delivered - timedelta(minutes=20),
            delivered_at=delivered if not cancelled else None,
            earning_cents=earn,
            tip_cents=tip,
            surge_multiplier=surge,
            distance_km=dist,
            payout_status=PayoutStatus.pending,
        )
        db.add(delivery)

    for row in demos:
        _add(*row)
    _add(*cancelled, cancelled=True)
