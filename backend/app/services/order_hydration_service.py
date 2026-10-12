"""Cache external order content onto our ``Order`` row before dispatch.

Partner-registered orders hold only the external order id. The rider app,
dispatch, ETA and completion code all read the mess, customer and drop-off from
our DB, so we copy them in from the external order API at assignment time.
Items are snapshots (``menu_item_id=None``); the external platform owns its
catalogue.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.enums import OrderStatus, PaymentStatus, UserRole
from app.models.mess import Mess
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.external_order import ExternalCustomer, ExternalMess, ExternalOrder, to_cents
from app.services import external_order_client
from app.services.external_order_client import ExternalOrderError, ExternalOrderNotFound
from app.services.otp_service import generate_otp

# Coordinates within ~11m are treated as the same pickup point.
COORD_EPS = 0.0001

# External order statuses that must never be dispatched.
BLOCKED_EXTERNAL_STATUSES = {"REJECTED", "CANCELLED", "CANCELED"}


def _match_or_create_mess(db: Session, m: ExternalMess, lat: float, lng: float) -> Mess:
    name = m.name.strip() or "Mess"
    existing = db.execute(
        select(Mess).where(
            Mess.name == name,
            Mess.lat.between(lat - COORD_EPS, lat + COORD_EPS),
            Mess.lng.between(lng - COORD_EPS, lng + COORD_EPS),
            Mess.is_test.is_(False),
        )
    ).scalars().first()
    if existing is not None:
        if m.contact_number:
            existing.contact_phone = m.contact_number
        if m.address.strip():
            existing.address_text = m.address.strip()[:255]
        return existing

    mess = Mess(
        owner_user_id=None,
        name=name,
        description="",
        address_text=m.address.strip()[:255],
        lat=lat,
        lng=lng,
        is_open=True,
        contact_phone=m.contact_number or "",
    )
    db.add(mess)
    db.flush()
    return mess


def _match_or_create_customer(db: Session, c: ExternalCustomer) -> User:
    phone = (c.contact_number or "").strip() or None
    if phone:
        existing = db.execute(select(User).where(User.phone == phone)).scalars().first()
        if existing is not None:
            return existing
    user = User(
        email=None,
        phone=phone,
        full_name=c.name.strip() or "Customer",
        hashed_password=hash_password("external-order-no-login"),
        roles=UserRole.customer.value,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _payment_status(raw: str | None) -> PaymentStatus:
    try:
        return PaymentStatus((raw or "").strip().lower())
    except ValueError:
        return PaymentStatus.pending


def fetch_or_http_error(order: Order) -> ExternalOrder:
    """Fetch the external order, mapping client errors to HTTP responses."""
    try:
        return external_order_client.fetch_order(order.external_order_ref or "")
    except ExternalOrderNotFound as exc:
        raise HTTPException(status_code=404, detail=f"External order not found: {exc}")
    except ExternalOrderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def hydrate_from_external(db: Session, order: Order) -> None:
    """Refresh the order's cached content from the external order API.

    No-op for orders that were not registered by external order id. Flushes but
    does not commit; the caller owns the transaction.
    """
    if not order.external_order_ref:
        return
    ext = fetch_or_http_error(order)
    c, m, d = ext.customer_details, ext.mess_details, ext.order_details

    status = (d.order_status or "").strip().upper()
    order.external_order_status = d.order_status
    if status in BLOCKED_EXTERNAL_STATUSES:
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"External order is {d.order_status}; it cannot be assigned",
        )
    if m.location.latitude is None or m.location.longitude is None:
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="External order has no mess coordinates; cannot dispatch a partner",
        )

    # Only (re)link the mess before dispatch starts; batches are keyed by mess.
    if order.status in (OrderStatus.placed, OrderStatus.accepted, OrderStatus.preparing) \
            or order.mess_id is None:
        order.mess_id = _match_or_create_mess(
            db, m, m.location.latitude, m.location.longitude
        ).id
    customer = _match_or_create_customer(db, c)
    order.customer_id = customer.id
    order.customer_phone = c.contact_number or customer.phone
    order.address_text = c.address.strip()[:255]
    order.address_lat = c.location.latitude
    order.address_lng = c.location.longitude
    order.customer_note = c.instruction.strip()[:512]

    subtotal = to_cents(d.item_total)
    delivery_fee = to_cents(d.delivery_charge)
    total = to_cents(d.grand_total)
    order.subtotal_cents = subtotal
    order.delivery_fee_cents = delivery_fee
    order.tax_cents = max(total - subtotal - delivery_fee, 0)
    order.total_cents = total
    order.payment_method = (d.payment_method or "")[:24] or order.payment_method
    order.payment_status = _payment_status(d.payment_status)

    order.items.clear()
    for it in d.order_items:
        unit = to_cents(it.price)
        order.items.append(
            OrderItem(
                menu_item_id=None,
                name_snapshot=it.name.strip()[:255] or "Item",
                unit_price_cents=unit,
                quantity=it.quantity,
                line_total_cents=unit * it.quantity,
            )
        )

    if order.placed_at is None:
        order.placed_at = utcnow()
    if not order.otp_code:
        order.otp_code = generate_otp()
        order.otp_expires_at = utcnow() + timedelta(minutes=settings.otp_expiry_minutes)
    db.flush()
