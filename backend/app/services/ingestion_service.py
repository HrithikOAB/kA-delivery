"""Booking-app order ingestion.

The second team's booking app pushes placed orders here for delivery. Orders
arrive with free-form item snapshots (the booking app owns its own catalogue),
so we do not reference this backend's ``MenuItem`` rows — items are stored as
snapshots with ``menu_item_id=None`` and totals are recomputed server-side.

Ingestion is idempotent on ``external_order_ref``: re-posting the same reference
returns the existing order instead of creating a duplicate.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.enums import OrderStatus, UserRole
from app.models.mess import Mess
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.integration import IngestOrderRequest
from app.services.order_service import TAX_RATE, _generate_otp

# Coordinates within ~11m are treated as the same pickup point.
_COORD_EPS = 0.0001


def _match_or_create_mess(db: Session, req: IngestOrderRequest) -> Mess:
    m = req.mess
    existing = db.execute(
        select(Mess).where(
            Mess.name == m.name,
            Mess.lat.between(m.lat - _COORD_EPS, m.lat + _COORD_EPS),
            Mess.lng.between(m.lng - _COORD_EPS, m.lng + _COORD_EPS),
            Mess.is_test.is_(False),
        )
    ).scalars().first()
    if existing is not None:
        # Keep contact details fresh.
        if m.contact_phone:
            existing.contact_phone = m.contact_phone
        if m.address_text:
            existing.address_text = m.address_text
        return existing

    mess = Mess(
        owner_user_id=None,
        name=m.name,
        description="",
        address_text=m.address_text,
        lat=m.lat,
        lng=m.lng,
        is_open=True,
        contact_phone=m.contact_phone,
        delivery_fee_cents=req.delivery_fee_cents,
    )
    db.add(mess)
    db.flush()
    return mess


def _match_or_create_customer(db: Session, req: IngestOrderRequest) -> User:
    phone = req.customer.phone.strip()
    existing = db.execute(
        select(User).where(User.phone == phone)
    ).scalars().first()
    if existing is not None:
        return existing
    user = User(
        email=None,
        phone=phone,
        full_name=req.customer.name.strip(),
        hashed_password=hash_password("booking-app-no-login"),
        roles=UserRole.customer.value,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def ingest_order(db: Session, req: IngestOrderRequest) -> tuple[Order, bool]:
    """Create (or return the existing) order for a booking-app reference.

    Returns ``(order, already_existed)``.
    """
    existing = db.execute(
        select(Order).where(Order.external_order_ref == req.external_order_ref)
    ).scalars().first()
    if existing is not None:
        return existing, True

    mess = _match_or_create_mess(db, req)
    customer = _match_or_create_customer(db, req)

    subtotal = sum(i.unit_price_cents * i.quantity for i in req.items)
    tax = round(subtotal * TAX_RATE)
    delivery_fee = req.delivery_fee_cents
    total = subtotal + tax + delivery_fee

    order = Order(
        customer_id=customer.id,
        mess_id=mess.id,
        status=OrderStatus.placed,
        source="booking_app",
        external_order_ref=req.external_order_ref,
        address_text=req.dropoff.address_text,
        address_lat=req.dropoff.lat,
        address_lng=req.dropoff.lng,
        customer_note=req.dropoff.note,
        customer_phone=customer.phone,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee,
        tax_cents=tax,
        total_cents=total,
        payment_method=req.payment_method,
        otp_code=_generate_otp(),
        otp_expires_at=utcnow() + timedelta(minutes=settings.otp_expiry_minutes),
        placed_at=utcnow(),
    )
    for i in req.items:
        order.items.append(
            OrderItem(
                menu_item_id=None,
                name_snapshot=i.name,
                unit_price_cents=i.unit_price_cents,
                quantity=i.quantity,
                line_total_cents=i.unit_price_cents * i.quantity,
                packaging_note=i.packaging_note,
            )
        )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order, False
