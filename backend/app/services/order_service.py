"""Order pricing and creation. Totals are ALWAYS computed here, server-side."""
from __future__ import annotations

import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import utcnow
from app.models.enums import OrderStatus
from app.models.mess import Mess, MenuItem
from app.models.order import Order, OrderItem
from app.models.user import Address, User
from app.schemas.order import (
    CartItemIn,
    CheckoutLine,
    CheckoutResponse,
    PlaceOrderRequest,
)
from app.services import notification_service, payment_service
from datetime import timedelta

TAX_RATE = 0.05  # 5% tax on subtotal


def _priced_lines(
    db: Session, mess: Mess, items: list[CartItemIn]
) -> tuple[list[CheckoutLine], int]:
    lines: list[CheckoutLine] = []
    subtotal = 0
    for item in items:
        menu_item = db.get(MenuItem, item.menu_item_id)
        if menu_item is None or menu_item.mess_id != mess.id:
            raise HTTPException(
                status_code=400,
                detail=f"Menu item {item.menu_item_id} is not on this mess's menu",
            )
        if not menu_item.is_available:
            raise HTTPException(
                status_code=409,
                detail=f"'{menu_item.name}' is currently unavailable",
            )
        line_total = menu_item.price_cents * item.quantity
        subtotal += line_total
        lines.append(
            CheckoutLine(
                menu_item_id=menu_item.id,
                name=menu_item.name,
                unit_price_cents=menu_item.price_cents,
                quantity=item.quantity,
                line_total_cents=line_total,
            )
        )
    return lines, subtotal


def price_cart(db: Session, mess_id: int, items: list[CartItemIn]) -> CheckoutResponse:
    mess = db.get(Mess, mess_id)
    if mess is None:
        raise HTTPException(status_code=404, detail="Mess not found")
    lines, subtotal = _priced_lines(db, mess, items)
    tax = round(subtotal * TAX_RATE)
    # Delivery fee is NULL until the mess owner configures one; treat as 0.
    delivery_fee = mess.delivery_fee_cents or 0
    total = subtotal + tax + delivery_fee
    return CheckoutResponse(
        mess_id=mess.id,
        lines=lines,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee,
        tax_cents=tax,
        total_cents=total,
    )


def _generate_otp() -> str:
    from app.services.otp_service import generate_otp

    return generate_otp()


def _resolve_address(
    db: Session, customer: User, req: PlaceOrderRequest
) -> tuple[str, float, float]:
    if req.address_id is not None:
        address = db.get(Address, req.address_id)
        if address is None or address.user_id != customer.id:
            raise HTTPException(status_code=404, detail="Address not found")
        return address.line1, address.lat, address.lng
    if (
        req.address_text is not None
        and req.address_lat is not None
        and req.address_lng is not None
    ):
        return req.address_text, req.address_lat, req.address_lng
    raise HTTPException(
        status_code=400,
        detail="Provide an address_id or inline address_text/lat/lng",
    )


def create_order(
    db: Session,
    customer: User,
    req: PlaceOrderRequest,
    *,
    is_test: bool = False,
    test_note: str | None = None,
) -> Order:
    """Create an order. Shared by the customer app (``is_test=False``) and the
    admin test-order tool (``is_test=True``); the only differences are the
    authorization at the route layer and the test safeguards enforced here:
    test orders never trigger real payment authorization, customer notifications,
    or other external side effects.
    """
    pricing = price_cart(db, req.mess_id, req.items)
    addr_text, addr_lat, addr_lng = _resolve_address(db, customer, req)
    mess = db.get(Mess, req.mess_id)

    order = Order(
        customer_id=customer.id,
        mess_id=req.mess_id,
        status=OrderStatus.placed,
        is_test=is_test,
        test_note=test_note,
        address_text=addr_text,
        address_lat=addr_lat,
        address_lng=addr_lng,
        subtotal_cents=pricing.subtotal_cents,
        delivery_fee_cents=pricing.delivery_fee_cents,
        tax_cents=pricing.tax_cents,
        total_cents=pricing.total_cents,
        payment_method="test" if is_test else req.payment_method,
        otp_code=_generate_otp(),
        otp_expires_at=utcnow() + timedelta(minutes=settings.otp_expiry_minutes),
        placed_at=utcnow(),
    )
    for line in pricing.lines:
        order.items.append(
            OrderItem(
                menu_item_id=line.menu_item_id,
                name_snapshot=line.name,
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
                line_total_cents=line.line_total_cents,
            )
        )
    # Test orders must not touch real payment/notification side effects.
    if not is_test:
        payment_service.authorize(order)
    db.add(order)
    db.commit()
    db.refresh(order)

    if not is_test and mess and mess.owner_user_id:
        notification_service.notify(
            mess.owner_user_id,
            "New order",
            f"Order #{order.id} placed — {order.total_cents/100:.2f}",
            {"order_id": order.id, "type": "new_order"},
        )
    return order
