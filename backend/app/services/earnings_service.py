"""Rider earnings and payout reconciliation."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.order import Order
from app.models.rider_incentive import RiderIncentive
from app.models.user import RiderProfile, User
from app.models.enums import DeliveryStatus, PayoutStatus
from app.schemas.delivery import (
    EarningLine,
    EarningsResponse,
    EarningsSummary,
)

DAY_SHORT = ["M", "T", "W", "T", "F", "S", "S"]
from app.config import settings

CASHOUT_FEE_CENTS = 500


def _start_of_day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(d: datetime | None = None) -> datetime:
    d = _start_of_day(d or datetime.utcnow())
    diff = (d.weekday())  # Monday=0
    return d - timedelta(days=diff)


def _add_days(d: datetime, n: int) -> datetime:
    return d + timedelta(days=n)


def _deliveries_for_earnings(db: Session, rider_id: int) -> list[Delivery]:
    """All completed deliveries count toward rider earnings (matches history)."""
    return db.execute(
        select(Delivery)
        .where(
            Delivery.rider_id == rider_id,
            Delivery.status == DeliveryStatus.delivered,
        )
        .order_by(Delivery.delivered_at.desc())
    ).scalars().all()


def _in_range(d: Delivery, start: datetime, end: datetime) -> bool:
    if not d.delivered_at:
        return False
    return start <= d.delivered_at < end


def _line_total(d: Delivery) -> int:
    return d.earning_cents + d.tip_cents


def summary_for_rider(db: Session, rider_id: int) -> EarningsResponse:
    deliveries = _deliveries_for_earnings(db, rider_id)
    now = datetime.utcnow()
    today_start = _start_of_day(now)
    today_end = _add_days(today_start, 1)
    today = [d for d in deliveries if _in_range(d, today_start, today_end)]

    total = sum(_line_total(d) for d in deliveries)
    pending = sum(_line_total(d) for d in deliveries if d.payout_status == PayoutStatus.pending)
    paid = sum(_line_total(d) for d in deliveries if d.payout_status == PayoutStatus.paid)

    lines = [
        EarningLine(
            delivery_id=d.id,
            order_id=d.order_id,
            amount_cents=_line_total(d),
            payout_status=d.payout_status.value,
            delivered_at=d.delivered_at,
        )
        for d in deliveries
    ]

    return EarningsResponse(
        summary=EarningsSummary(
            total_deliveries=len(deliveries),
            total_earned_cents=total,
            today_deliveries=len(today),
            today_earned_cents=sum(_line_total(d) for d in today),
            pending_payout_cents=pending,
            paid_payout_cents=paid,
        ),
        lines=lines,
    )


def reconcile_batch_payout(db: Session, deliveries: list[Delivery]) -> int:
    """Mark a completed batch's deliveries as paid out and return the total.

    This is the diagram's final "reconcile payout" step; in production it would
    hand off to a real payout provider.
    """
    total = 0
    for d in deliveries:
        if d.status == DeliveryStatus.delivered:
            d.payout_status = PayoutStatus.paid
            total += d.earning_cents
    return total


def _week_range_label(start: datetime) -> str:
    end = _add_days(start, 6)
    return f"{start.strftime('%b %d')} – {end.strftime('%b %d')}"


def _next_tuesday_label(from_dt: datetime | None = None) -> str:
    d = _start_of_day(from_dt or datetime.utcnow())
    days_until = (1 - d.weekday()) % 7  # Tuesday=1
    if days_until == 0:
        days_until = 7
    nxt = d + timedelta(days=days_until)
    return nxt.strftime("%A, %b %d")


def _deliveries_for_earnings(db: Session, rider_id: int) -> list[Delivery]:
    """All completed deliveries count toward rider earnings (matches history)."""
    return db.execute(
        select(Delivery)
        .where(
            Delivery.rider_id == rider_id,
            Delivery.status == DeliveryStatus.delivered,
        )
        .order_by(Delivery.delivered_at.desc())
    ).scalars().all()


def _in_range(d: Delivery, start: datetime, end: datetime) -> bool:
    if not d.delivered_at:
        return False
    return start <= d.delivered_at < end


def _line_total(d: Delivery) -> int:
    return d.earning_cents + d.tip_cents


def _online_minutes(deliveries: list[Delivery]) -> int:
    tracked = sum(d.active_minutes or 0 for d in deliveries)
    if tracked > 0:
        return tracked
    return len(deliveries) * 42 + (60 if deliveries else 0)


def _format_duration(minutes: int) -> str:
    if minutes <= 0:
        return "—"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def detail_for_rider(db: Session, rider_id: int, view: str = "weekly") -> dict:
    now = datetime.utcnow()
    deliveries = _deliveries_for_earnings(db, rider_id)
    user = db.get(User, rider_id)
    profile = user.rider_profile if user else None

    week_start = _start_of_week(now)
    week_end = _add_days(week_start, 7)
    prev_start = _add_days(week_start, -7)
    prev_end = week_start

    week_deliveries = [d for d in deliveries if _in_range(d, week_start, week_end)]
    prev_deliveries = [d for d in deliveries if _in_range(d, prev_start, prev_end)]

    week_total = sum(_line_total(d) for d in week_deliveries)
    prev_total = sum(_line_total(d) for d in prev_deliveries)
    pct_change = ((week_total - prev_total) / prev_total * 100) if prev_total > 0 else (100.0 if week_total > 0 else 0.0)

    buckets = []
    for i in range(7):
        day = _add_days(week_start, i)
        nxt = _add_days(day, 1)
        day_deliveries = [d for d in week_deliveries if _in_range(d, day, nxt)]
        amount = sum(_line_total(d) for d in day_deliveries)
        buckets.append({
            "key": day.date().isoformat(),
            "label": day.strftime("%A"),
            "short": DAY_SHORT[i],
            "amount_cents": amount,
            "trips": len(day_deliveries),
            "is_today": day.date() == now.date(),
        })

    peak = max(buckets, key=lambda b: b["amount_cents"]) if buckets else None
    trips = len(week_deliveries)
    online_minutes = _online_minutes(week_deliveries)
    avg_per_delivery = round(week_total / trips) if trips > 0 else 0

    today_start = _start_of_day(now)
    today_end = _add_days(today_start, 1)
    today_deliveries = [d for d in deliveries if _in_range(d, today_start, today_end)]
    today_total = sum(_line_total(d) for d in today_deliveries)

    hourly = []
    if view == "daily":
        for hour in range(6, 24):
            h_start = today_start.replace(hour=hour)
            h_end = today_start.replace(hour=hour + 1) if hour < 23 else today_end
            h_deliveries = [d for d in today_deliveries if d.delivered_at and h_start <= d.delivered_at < h_end]
            hourly.append({
                "key": str(hour),
                "label": f"{hour:02d}:00",
                "short": f"{hour % 12 or 12}{'a' if hour < 12 else 'p'}",
                "amount_cents": sum(_line_total(d) for d in h_deliveries),
                "trips": len(h_deliveries),
                "is_today": True,
            })

    pending = sum(d.earning_cents + d.tip_cents for d in deliveries if d.payout_status == PayoutStatus.pending)

    incentives = db.execute(
        select(RiderIncentive).where(RiderIncentive.rider_id == rider_id).order_by(RiderIncentive.id)
    ).scalars().all()

    daily_map: dict[str, dict] = {}
    for d in deliveries:
        if not d.delivered_at:
            continue
        key = d.delivered_at.date().isoformat()
        if key not in daily_map:
            day = d.delivered_at
            is_today = day.date() == now.date()
            is_sat = day.weekday() == 5
            daily_map[key] = {
                "key": key,
                "date": day,
                "title": "Today" if is_today else day.strftime("%A"),
                "badge": "Sunday" if day.weekday() == 6 and is_today else ("Saturday" if is_sat else day.strftime("%b %d")),
                "amount_cents": 0,
                "tip_cents": 0,
                "trips": 0,
                "online_minutes": 0,
                "tag": None,
            }
        daily_map[key]["amount_cents"] += _line_total(d)
        daily_map[key]["tip_cents"] += d.tip_cents
        daily_map[key]["trips"] += 1
        daily_map[key]["online_minutes"] += d.active_minutes or 42

    recent_daily = []
    for key in sorted(daily_map.keys(), reverse=True)[:5]:
        row = daily_map[key]
        day = row["date"]
        is_today = day.date() == now.date()
        is_sat = day.weekday() == 5
        amount = row["amount_cents"]
        tag = None
        if is_today:
            tag = f"incl. {money_label(row['tip_cents'])} tips" if row["tip_cents"] else None
        elif is_sat and amount >= 150000:
            tag = "Peak Saturday"
        else:
            tag = "Standard Shift"
        recent_daily.append({
            "key": key,
            "title": row["title"],
            "badge": row["badge"],
            "subtitle": f"{row['trips']} deliveries · {_format_duration(row['online_minutes'])} online",
            "amount_cents": amount,
            "trips": row["trips"],
            "online_label": _format_duration(row["online_minutes"]),
            "tip_cents": row["tip_cents"],
            "tag": tag,
            "icon": "today" if is_today else ("weekend" if day.weekday() in (5, 6) else "weekday"),
        })

    bank_name = profile.bank_name if profile else ""
    bank_masked = profile.bank_account_masked if profile else ""

    return {
        "view": view,
        "summary": {
            "total_deliveries": len(deliveries),
            "total_earned_cents": sum(_line_total(d) for d in deliveries),
            "pending_payout_cents": pending,
            "paid_payout_cents": sum(_line_total(d) for d in deliveries if d.payout_status == PayoutStatus.paid),
        },
        "weekly": {
            "range_label": _week_range_label(week_start),
            "total_cents": week_total,
            "pct_change": round(pct_change, 1),
            "trips": trips,
            "online_minutes": online_minutes,
            "online_label": _format_duration(online_minutes),
            "avg_per_delivery_cents": avg_per_delivery,
            "buckets": buckets,
            "peak": peak,
        },
        "daily": {
            "total_cents": today_total,
            "trips": len(today_deliveries),
            "online_minutes": _online_minutes(today_deliveries),
            "online_label": _format_duration(_online_minutes(today_deliveries)),
            "buckets": hourly,
        },
        "payout": {
            "cycle_label": "Weekly Cycle",
            "cycle_subtitle": "Auto-clears every Tuesday",
            "next_date_label": _next_tuesday_label(now),
            "amount_cents": pending,
            "bank_name": bank_name,
            "bank_account_masked": bank_masked,
            "bank_verified": bool(profile and profile.upi_linked),
            "cashout_fee_cents": CASHOUT_FEE_CENTS,
        },
        "incentives": [
            {
                "id": inc.id,
                "incentive_type": inc.incentive_type,
                "title": inc.title,
                "subtitle": inc.subtitle,
                "target_value": inc.target_value,
                "current_value": inc.current_value,
                "bonus_cents": inc.bonus_cents,
                "status": inc.status,
                "progress_pct": round(min(100, inc.current_value / inc.target_value * 100)) if inc.target_value else 100,
                "trips_remaining": max(0, inc.target_value - inc.current_value),
                "ends_at": inc.ends_at,
            }
            for inc in incentives
        ],
        "recent_daily": recent_daily,
        "active_incentive_count": sum(1 for inc in incentives if inc.status == "active"),
    }


def money_label(cents: int) -> str:
    rupees = cents / 100
    if rupees % 1 == 0:
        return f"₹{rupees:.0f}"
    return f"₹{rupees:.2f}"


def instant_cashout(db: Session, rider_id: int) -> dict:
    deliveries = _deliveries_for_earnings(db, rider_id)
    pending = [d for d in deliveries if d.payout_status == PayoutStatus.pending]
    amount = sum(_line_total(d) for d in pending)
    if amount <= CASHOUT_FEE_CENTS:
        return {"ok": False, "message": "Insufficient balance for cashout"}
    from app.models.rider_cashout import RiderCashout
    for d in pending:
        d.payout_status = PayoutStatus.paid
    cashout = RiderCashout(
        rider_id=rider_id,
        amount_cents=amount - CASHOUT_FEE_CENTS,
        fee_cents=CASHOUT_FEE_CENTS,
        status="completed",
    )
    db.add(cashout)
    db.commit()
    return {
        "ok": True,
        "amount_cents": amount - CASHOUT_FEE_CENTS,
        "fee_cents": CASHOUT_FEE_CENTS,
        "message": f"₹{(amount - CASHOUT_FEE_CENTS) / 100:.2f} deposited instantly",
    }


def seed_earnings_demo(db: Session, rider_id: int, customer_id: int, default_mess_id: int) -> None:
    """Seed weekly earnings spread + incentives for the partner earnings screen."""
    from sqlalchemy import select
    from app.models.delivery import Delivery, DeliveryBatch
    from app.models.enums import BatchStatus, DeliveryStatus, OrderStatus, PaymentStatus, PayoutStatus
    from app.models.mess import Mess
    from app.models.order import Order

    marker = db.execute(
        select(Delivery).where(Delivery.rider_id == rider_id, Delivery.order_id == 100)
    ).scalar_one_or_none()
    if marker:
        return

    default_mess = db.get(Mess, default_mess_id)
    if not default_mess:
        return

    now = datetime.utcnow()
    week_start = _start_of_week(now)

    # amounts per day Mon-Sun (cents) matching design vibe
    daily_plan = [
        (0, 3, 120000, 0),    # Mon
        (1, 4, 145000, 0),    # Tue
        (2, 5, 160000, 0),    # Wed
        (3, 4, 138000, 0),    # Thu
        (4, 10, 165000, 1800000),  # Fri - design 1.65k
        (5, 12, 198000, 1980000),  # Sat - design 1.98k peak
        (6, 8, 142050, 1420050),   # Sun - design 1,420.50
    ]

    order_id = 100
    for day_offset, trip_count, day_total, _ in daily_plan:
        per_trip = day_total // trip_count if trip_count else 0
        day = week_start + timedelta(days=day_offset)
        for t in range(trip_count):
            delivered = day.replace(hour=min(22, 10 + t), minute=(15 + t * 7) % 60)
            earn = per_trip + (t % 3) * 200
            tip = 1500 if (day_offset == 6 and t < 3) else (2000 if t % 4 == 0 else 0)
            order = Order(
                id=order_id,
                customer_id=customer_id,
                mess_id=default_mess_id,
                status=OrderStatus.delivered,
                is_test=True,
                test_note="demo-earnings",
                address_text=f"Flat {t+1}, Koramangala, Bengaluru",
                address_lat=12.93 + day_offset * 0.001,
                address_lng=77.62 + t * 0.001,
                subtotal_cents=12000,
                delivery_fee_cents=2000,
                total_cents=14000,
                payment_status=PaymentStatus.paid,
                placed_at=delivered - timedelta(minutes=50),
                delivered_at=delivered,
            )
            db.add(order)
            db.flush()
            batch = DeliveryBatch(
                mess_id=default_mess_id,
                rider_id=rider_id,
                status=BatchStatus.completed,
                picked_up_at=delivered - timedelta(minutes=25),
                completed_at=delivered,
                total_earning_cents=earn,
            )
            db.add(batch)
            db.flush()
            db.add(Delivery(
                order_id=order.id,
                batch_id=batch.id,
                rider_id=rider_id,
                status=DeliveryStatus.delivered,
                delivered_at=delivered,
                base_fare_cents=settings.rider_base_fare_cents,
                earning_cents=earn,
                tip_cents=tip,
                active_minutes=38 + t * 2,
                payout_status=PayoutStatus.pending,
            ))
            order_id += 1

    existing = db.execute(
        select(RiderIncentive).where(RiderIncentive.rider_id == rider_id)
    ).scalars().first()
    if not existing:
        db.add(RiderIncentive(
            rider_id=rider_id,
            incentive_type="weekend_rush",
            title="Weekend Rush Target",
            subtitle="Complete 30 weekend peak orders for a +₹600 bonus",
            target_value=30,
            current_value=22,
            bonus_cents=60000,
            status="active",
            ends_at=now + timedelta(days=2),
        ))
        db.add(RiderIncentive(
            rider_id=rider_id,
            incentive_type="zero_spill",
            title="Zero-Spill Bonus",
            subtitle="100% spill-free handling this week",
            target_value=1,
            current_value=1,
            bonus_cents=30000,
            status="awarded",
        ))
