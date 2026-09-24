"""Admin-only test-delivery tool.

Creates a clearly-marked **TEST** order that flows through the *real* backend
pipeline (pricing, state machine, dispatch, tracking) so delivery operations can
be exercised end-to-end without a real customer account or payment.

Reuses ``order_service.create_order`` (the same path the future customer app
uses) with ``is_test=True``; the pickup is modelled as a lightweight test
``Mess`` at the chosen coordinates so dispatch and tracking work unchanged.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.base import utcnow
from app.models.delivery import Delivery, DeliveryBatch, DeliveryOffer
from app.models.enums import (
    BatchStatus,
    DeliveryStatus,
    OfferStatus,
    OrderStatus,
    UserRole,
)
from app.models.mess import Mess, MenuItem
from app.models.order import Order
from app.models.user import User
from app.schemas.admin import TestDeliveryCreate, TestDeliveryOut
from app.schemas.order import CartItemIn, PlaceOrderRequest
from app.services import audit_service, dispatch_service, order_service, state_machine
from app.services.state_machine import InvalidTransition
from app.services.ws_manager import manager

_TEST_CUSTOMER_EMAIL = "test-customer@digimess.app"
_TEST_ITEM_PRICE_CENTS = 10000  # nominal ₹100 test item


def _test_customer(db: Session) -> User:
    """A single shared placeholder customer that owns all test orders."""
    user = db.execute(
        select(User).where(User.email == _TEST_CUSTOMER_EMAIL)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=_TEST_CUSTOMER_EMAIL,
            full_name="Test Customer",
            phone=None,
            hashed_password=hash_password("test-only-no-login"),
            roles=UserRole.customer.value,
            is_active=False,  # placeholder cannot log in
        )
        db.add(user)
        db.flush()
    return user


def _test_pickup_mess(db: Session, req: TestDeliveryCreate) -> Mess:
    """Create a fresh test pickup 'mess' at the chosen coordinates."""
    mess = Mess(
        owner_user_id=None,
        name=req.pickup_label or "TEST Pickup",
        description=req.pickup_instructions or "Test pickup point",
        address_text=req.pickup_label or "TEST Pickup",
        lat=req.pickup_lat,
        lng=req.pickup_lng,
        is_open=True,
        is_test=True,
        delivery_fee_cents=0,
    )
    db.add(mess)
    db.flush()
    item = MenuItem(
        mess_id=mess.id,
        name="Test Item",
        description="Synthetic item for a test delivery",
        category="Test",
        price_cents=_TEST_ITEM_PRICE_CENTS,
        is_available=True,
    )
    db.add(item)
    db.flush()
    return mess


def create_test_delivery(
    db: Session, admin: User, req: TestDeliveryCreate
) -> Order:
    customer = _test_customer(db)
    mess = _test_pickup_mess(db, req)
    item = db.execute(
        select(MenuItem).where(MenuItem.mess_id == mess.id)
    ).scalars().first()

    dropoff_text = req.dropoff_label or "TEST Drop-off"
    if req.customer_name:
        dropoff_text = f"{dropoff_text} — {req.customer_name}"

    note_bits = ["TEST"]
    if req.customer_name:
        note_bits.append(f"customer={req.customer_name}")
    if req.customer_contact:
        note_bits.append(f"contact={req.customer_contact}")
    if req.delivery_instructions:
        note_bits.append(f"instructions={req.delivery_instructions}")
    test_note = " • ".join(note_bits)[:255]

    place = PlaceOrderRequest(
        mess_id=mess.id,
        items=[CartItemIn(menu_item_id=item.id, quantity=1)],
        address_text=dropoff_text,
        address_lat=req.dropoff_lat,
        address_lng=req.dropoff_lng,
        payment_method="test",
    )
    order = order_service.create_order(
        db, customer, place, is_test=True, test_note=test_note
    )
    audit_service.record(
        db,
        actor_user_id=admin.id,
        action="test_order_created",
        target_type="order",
        target_id=order.id,
        detail=f"pickup=({req.pickup_lat},{req.pickup_lng}) drop=({req.dropoff_lat},{req.dropoff_lng})",
        order_id=order.id,
    )
    db.commit()
    db.refresh(order)
    return order


def advance(db: Session, order_id: int, admin: User, to: str) -> Order:
    """Drive a test order through the real mess/dispatch pipeline.

    ``to`` is one of 'accept' | 'prepare' | 'ready'. Marking it ready batches and
    offers the delivery to an eligible online rider (the normal dispatch path).
    """
    order = _test_order(db, order_id)
    try:
        if to == "accept":
            state_machine.transition_order(db, order, OrderStatus.accepted, actor_user_id=admin.id)
            dispatch_service.allocate_on_mess_accept(db, order)
            dispatch_service.repair_assigned_batches(db)
        elif to == "prepare":
            state_machine.transition_order(db, order, OrderStatus.preparing, actor_user_id=admin.id)
            dispatch_service.ensure_missing_deliveries(db)
        elif to == "ready":
            state_machine.transition_order(db, order, OrderStatus.ready, actor_user_id=admin.id)
            batch = dispatch_service.ensure_batch_for_ready_order(db, order)
            if batch.rider_id is None:
                dispatch_service.offer_batch_to_next_rider(db, batch)
            else:
                dispatch_service.assign_order_if_rider_ready(db, order, batch)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown advance step '{to}'")
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order


def assign_to_rider(db: Session, order_id: int, admin: User, rider_id: int) -> Order:
    """Manually offer the test delivery to a specific approved partner.

    The partner receives it via ``/rider/offers`` and accepts through the normal
    flow (no dispatch mechanism is invented). Drives the order to ``ready`` first
    if needed so a batch exists.
    """
    order = _test_order(db, order_id)
    rider = db.get(User, rider_id)
    if rider is None or rider.rider_profile is None or not rider.rider_profile.is_approved:
        raise HTTPException(status_code=400, detail="Choose an approved partner")

    # Ensure the order is batched (advance through the pipeline if still early).
    try:
        while order.status in (OrderStatus.placed, OrderStatus.accepted, OrderStatus.preparing):
            nxt = {
                OrderStatus.placed: OrderStatus.accepted,
                OrderStatus.accepted: OrderStatus.preparing,
                OrderStatus.preparing: OrderStatus.ready,
            }[order.status]
            state_machine.transition_order(db, order, nxt, actor_user_id=admin.id)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    batch = dispatch_service.ensure_batch_for_ready_order(db, order)
    if batch.rider_id is not None and batch.rider_id != rider.id:
        raise HTTPException(status_code=409, detail="Delivery is already assigned to another partner")

    # Exclusive-offer policy: do not yank a live offer from a different partner.
    # They must respond (or the offer must lapse/reject) before re-offering.
    if any(
        off.status == OfferStatus.sent and off.rider_id != rider.id
        for off in batch.offers
    ):
        raise HTTPException(
            status_code=409,
            detail="This delivery is already offered to another partner. Wait for them to respond, or cancel that offer first.",
        )

    # Clear any prior open offers for this batch, then offer to the chosen rider.
    for off in list(batch.offers):
        if off.status == OfferStatus.sent:
            off.status = OfferStatus.expired
            off.responded_at = utcnow()
    dispatch_service.create_offer(db, batch, rider)
    audit_service.record(
        db, actor_user_id=admin.id, action="test_order_assigned",
        target_type="order", target_id=order.id, order_id=order.id,
        detail=f"offered to rider {rider.id}",
    )
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order


def cancel(db: Session, order_id: int, admin: User, reason: str | None = None) -> Order:
    """Safely cancel/reset a test delivery: cancels the order, its batch and any
    deliveries, and revokes tracking. Reuses the state machine.
    """
    order = _test_order(db, order_id)
    if order.status in (OrderStatus.delivered, OrderStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Order already {order.status.value}")
    try:
        state_machine.transition_order(
            db, order, OrderStatus.cancelled, actor_user_id=admin.id,
            detail=(reason or "test cancel"),
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    order.cancelled_reason = reason or "test cancel"

    delivery = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()
    if delivery is not None:
        if delivery.status not in (DeliveryStatus.delivered, DeliveryStatus.cancelled):
            delivery.status = DeliveryStatus.cancelled
        batch = db.get(DeliveryBatch, delivery.batch_id)
        if batch is not None:
            batch.status = BatchStatus.cancelled
            for off in batch.offers:
                if off.status == OfferStatus.sent:
                    off.status = OfferStatus.expired
    audit_service.record(
        db, actor_user_id=admin.id, action="test_order_cancelled",
        target_type="order", target_id=order.id, reason=reason, order_id=order.id,
    )
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order


def _test_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.is_test:
        # The admin test tool only ever operates on test orders — never on real
        # customer orders.
        raise HTTPException(status_code=403, detail="Not a test order")
    return order


def to_out(db: Session, order: Order) -> TestDeliveryOut:
    mess = db.get(Mess, order.mess_id)
    delivery = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()
    rider = db.get(User, delivery.rider_id) if delivery and delivery.rider_id else None
    return TestDeliveryOut(
        order_id=order.id,
        is_test=order.is_test,
        status=order.status.value,
        pickup_label=mess.name if mess else "",
        pickup_lat=mess.lat if mess else 0.0,
        pickup_lng=mess.lng if mess else 0.0,
        dropoff_label=order.address_text,
        dropoff_lat=order.address_lat,
        dropoff_lng=order.address_lng,
        test_note=order.test_note,
        rider_id=rider.id if rider else None,
        rider_name=rider.full_name if rider else None,
        delivery_status=delivery.status.value if delivery else None,
        otp_code=order.otp_code,
        created_at=order.created_at,
    )
