"""Rider home dashboard: today's totals and the last completed delivery."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.enums import DeliveryStatus
from app.models.mess import Mess
from app.models.order import Order
from app.services.earnings_service import summary_for_rider
from app.services.order_labels import order_ref


def _ago_label(dt: datetime | None) -> str:
    if dt is None:
        return ""
    mins = int((datetime.utcnow() - dt).total_seconds() // 60)
    if mins < 1:
        return "Just now"
    if mins < 60:
        return f"{mins} mins ago"
    return f"{mins // 60}h ago"


def build_dashboard(db: Session, rider_id: int) -> dict:
    earnings = summary_for_rider(db, rider_id)

    last_completed = None
    last_row = db.execute(
        select(Delivery, Order, Mess)
        .join(Order, Delivery.order_id == Order.id)
        .join(Mess, Order.mess_id == Mess.id)
        .where(
            Delivery.rider_id == rider_id,
            Delivery.status == DeliveryStatus.delivered,
        )
        .order_by(Delivery.delivered_at.desc())
        .limit(1)
    ).first()
    if last_row:
        delivery, order, mess = last_row
        last_completed = {
            "mess_name": mess.name,
            "ticket_ref": order_ref(order),
            "item_count": sum(i.quantity for i in order.items),
            "amount_cents": delivery.earning_cents + delivery.tip_cents,
            "completed_at": delivery.delivered_at.isoformat() if delivery.delivered_at else "",
            "completed_ago_label": _ago_label(delivery.delivered_at),
        }

    return {
        "today_deliveries": earnings.summary.today_deliveries,
        "today_earnings_cents": earnings.summary.today_earned_cents,
        "last_completed": last_completed,
    }
