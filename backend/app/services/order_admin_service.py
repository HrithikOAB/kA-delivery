"""Admin order operations: rich detail, candidate riders, and assignment.

Assignment reuses the existing dispatch engine (batches + offers) rather than
inventing a new mechanism:
- **Internal (KA)**: offer the order to the chosen approved rider; the rider
  accepts in-app through the normal offer flow (``dispatch_service.create_offer``
  / ``accept_offer``).
- **External (Zomato/Swiggy/other)**: record the handoff on the order, close any
  internal batch/offers, and let ops track status manually.

The "one rider, one mess at a time" rule is enforced here: a rider carrying an
active order from a *different* mess cannot be offered a new one. Same-mess
orders are allowed (batching).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.delivery import Delivery, DeliveryBatch, DeliveryOffer
from app.models.enums import (
    ACTIVE_ORDER_STATUSES,
    BatchStatus,
    DeliveryStatus,
    OfferStatus,
    OrderStatus,
    UserRole,
)
from app.models.mess import Mess
from app.models.order import Order
from app.models.tracking import AuditEvent
from app.models.user import RiderProfile, User
from app.services import (
    audit_service,
    dispatch_service,
    location_service,
    notification_service,
    presence_service,
    state_machine,
)
from app.services.eta_service import haversine_km
from app.services.state_machine import InvalidTransition
from app.services.ws_manager import manager


# --- Helpers --------------------------------------------------------------

def _delivery_for(db: Session, order_id: int) -> Delivery | None:
    return db.execute(
        select(Delivery).where(Delivery.order_id == order_id)
    ).scalar_one_or_none()


def _rider_active_order(db: Session, rider_id: int) -> tuple[int, int] | None:
    """Return (order_id, mess_id) of the rider's most recent active order, if any."""
    row = db.execute(
        select(Order.id, Order.mess_id)
        .join(Delivery, Delivery.order_id == Order.id)
        .where(
            Delivery.rider_id == rider_id,
            Order.status.in_(list(ACTIVE_ORDER_STATUSES)),
        )
        .order_by(Order.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


# --- Order detail ---------------------------------------------------------

def build_order_detail(db: Session, order: Order) -> dict:
    """Assemble the full admin order-detail payload (see ``OrderDetailOut``)."""
    mess = db.get(Mess, order.mess_id)
    customer = db.get(User, order.customer_id)
    delivery = _delivery_for(db, order.id)
    batch = db.get(DeliveryBatch, delivery.batch_id) if delivery else None
    rider = db.get(User, delivery.rider_id) if delivery and delivery.rider_id else None

    offer_pending = False
    offered_rider_id: int | None = None
    if batch is not None and batch.rider_id is None:
        open_offer = db.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.batch_id == batch.id,
                DeliveryOffer.status == OfferStatus.sent,
            )
        ).scalars().first()
        if open_offer is not None:
            offer_pending = True
            offered_rider_id = open_offer.rider_id

    assignment = {
        "rider_id": rider.id if rider else None,
        "rider_name": rider.full_name if rider else None,
        "rider_phone": rider.phone if rider else None,
        "delivery_status": delivery.status.value if delivery else None,
        "batch_status": batch.status.value if batch else None,
        "offer_pending": offer_pending,
        "offered_rider_id": offered_rider_id,
    }

    return {
        "order_id": order.id,
        "is_test": order.is_test,
        "status": order.status.value,
        "mess_name": mess.name if mess else None,
        "customer_name": customer.full_name if customer else None,
        "rider_name": rider.full_name if rider else None,
        "delivery_status": delivery.status.value if delivery else None,
        "total_cents": order.total_cents,
        "created_at": order.created_at,
        "fulfillment_type": order.fulfillment_type,
        "external_provider": order.external_provider,
        "dropoff_text": order.address_text,
        "subtotal_cents": order.subtotal_cents,
        "delivery_fee_cents": order.delivery_fee_cents,
        "tax_cents": order.tax_cents,
        "payment_status": order.payment_status.value,
        "payment_method": order.payment_method,
        "external_reference": order.external_reference,
        "external_note": order.external_note,
        "external_status": order.external_status,
        "source": order.source,
        "mess": (
            {
                "mess_id": mess.id,
                "name": mess.name,
                "address_text": mess.address_text,
                "lat": mess.lat,
                "lng": mess.lng,
                "contact_phone": mess.contact_phone,
            }
            if mess
            else None
        ),
        "customer": {
            "name": customer.full_name if customer else "",
            "phone": order.customer_phone or (customer.phone if customer else None),
            "dropoff_text": order.address_text,
            "dropoff_lat": order.address_lat,
            "dropoff_lng": order.address_lng,
            "note": order.customer_note or "",
        },
        "items": [
            {
                "name": it.name_snapshot,
                "unit_price_cents": it.unit_price_cents,
                "quantity": it.quantity,
                "line_total_cents": it.line_total_cents,
            }
            for it in order.items
        ],
        "assignment": assignment,
        "timeline": audit_service.for_order(db, order.id),
        # issues are attached by the route (reuses its existing query).
    }


# --- Candidate riders -----------------------------------------------------

def candidate_riders(db: Session, order: Order) -> list[dict]:
    """Approved, online riders ranked by distance to the order's mess.

    A rider carrying an active order from a *different* mess is still returned
    but flagged ``available=False`` so the UI can block the assignment.
    """
    mess = db.get(Mess, order.mess_id)
    if mess is None:
        return []

    # Take stale (force-closed) riders offline first so the list is genuine.
    presence_service.sweep_stale_online(db)
    profiles = db.execute(
        select(RiderProfile).where(RiderProfile.is_online.is_(True))
    ).scalars().all()

    out: list[dict] = []
    for profile in profiles:
        if not profile.is_approved:
            continue
        user = db.get(User, profile.user_id)
        if user is None or not user.is_active or not user.has_role(UserRole.rider):
            continue

        if profile.last_lat is not None and profile.last_lng is not None:
            distance = round(
                haversine_km(profile.last_lat, profile.last_lng, mess.lat, mess.lng), 2
            )
        else:
            distance = None

        active = _rider_active_order(db, profile.user_id)
        active_order_id = active[0] if active else None
        active_mess_id = active[1] if active else None
        available = active is None or active_mess_id == order.mess_id
        reason = None if available else "On another mess's order"

        latest = location_service.latest_location(db, profile.user_id)
        out.append(
            {
                "rider_id": profile.user_id,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_online": profile.is_online,
                "rating": round(float(profile.rating), 2) if profile.rating is not None else None,
                "vehicle_type": profile.vehicle_type,
                "distance_km": distance,
                "location_is_stale": (
                    location_service.is_stale(latest) if latest else True
                ),
                "active_order_id": active_order_id,
                "active_mess_id": active_mess_id,
                "available": available,
                "unavailable_reason": reason,
            }
        )

    # Nearest first; unknown distance sorts last.
    out.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0.0))
    return out


# --- Assignment -----------------------------------------------------------

def offer_order_to_rider(
    db: Session,
    order: Order,
    rider: User,
    *,
    actor_user_id: int,
    audit_action: str,
) -> DeliveryBatch:
    """Offer an order's delivery to a specific rider (shared by admin + test tool).

    Advances the order through the kitchen pipeline to ``ready`` if needed so a
    batch exists, guards against yanking another rider's live offer, then creates
    the offer. The rider accepts through the normal ``/rider/offers`` flow.
    """
    if rider.rider_profile is None or not rider.rider_profile.is_approved:
        raise HTTPException(status_code=400, detail="Choose an approved partner")

    try:
        while order.status in (
            OrderStatus.placed,
            OrderStatus.accepted,
            OrderStatus.preparing,
        ):
            nxt = {
                OrderStatus.placed: OrderStatus.accepted,
                OrderStatus.accepted: OrderStatus.preparing,
                OrderStatus.preparing: OrderStatus.ready,
            }[order.status]
            state_machine.transition_order(db, order, nxt, actor_user_id=actor_user_id)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    batch = dispatch_service.ensure_batch_for_ready_order(db, order)
    if batch.rider_id is not None and batch.rider_id != rider.id:
        raise HTTPException(
            status_code=409, detail="Delivery is already assigned to another partner"
        )

    # Exclusive-offer policy: do not yank a live offer from a different partner.
    if any(
        off.status == OfferStatus.sent and off.rider_id != rider.id
        for off in batch.offers
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "This delivery is already offered to another partner. Wait for "
                "them to respond, or cancel that offer first."
            ),
        )

    # Clear any prior open offers for this batch, then offer to the chosen rider.
    for off in list(batch.offers):
        if off.status == OfferStatus.sent:
            off.status = OfferStatus.expired
            off.responded_at = utcnow()
    dispatch_service.create_offer(db, batch, rider)
    audit_service.record(
        db,
        actor_user_id=actor_user_id,
        action=audit_action,
        target_type="order",
        target_id=order.id,
        order_id=order.id,
        detail=f"offered to rider {rider.id}",
    )
    return batch


def assign_internal(db: Session, order: Order, admin: User, rider_id: int) -> Order:
    """Offer the order to an in-platform (KA) rider, enforcing the mess rule."""
    if order.status in (OrderStatus.delivered, OrderStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Order already {order.status.value}")

    rider = db.get(User, rider_id)
    if rider is None or rider.rider_profile is None or not rider.rider_profile.is_approved:
        raise HTTPException(status_code=400, detail="Choose an approved partner")

    active = _rider_active_order(db, rider_id)
    if active is not None and active[1] != order.mess_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Partner is already delivering order #{active[0]} from another "
                "mess. A partner can only carry orders from one mess at a time."
            ),
        )

    order.fulfillment_type = "internal"
    # Clear any prior external handoff if the order is being re-routed to KA.
    order.external_provider = None
    order.external_status = None
    order.external_reference = None
    order.external_note = None
    order.external_assigned_at = None

    offer_order_to_rider(
        db, order, rider, actor_user_id=admin.id, audit_action="order_assigned"
    )
    if not order.is_test:
        notification_service.notify(
            rider.id,
            "New delivery offer",
            f"Order #{order.id} is available for you to accept.",
            {"order_id": order.id, "type": "delivery_offer"},
        )
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order


def _close_internal_dispatch(db: Session, order: Order) -> None:
    """Cancel any internal batch/delivery/open offers for an order (external handoff)."""
    delivery = _delivery_for(db, order.id)
    if delivery is None:
        return
    if delivery.status not in (DeliveryStatus.delivered, DeliveryStatus.cancelled):
        delivery.status = DeliveryStatus.cancelled
    delivery.rider_id = None
    batch = db.get(DeliveryBatch, delivery.batch_id)
    if batch is not None:
        batch.status = BatchStatus.cancelled
        batch.rider_id = None
        for off in batch.offers:
            if off.status == OfferStatus.sent:
                off.status = OfferStatus.expired
                off.responded_at = utcnow()


def assign_external(
    db: Session,
    order: Order,
    admin: User,
    provider: str,
    reference: str | None,
    note: str | None,
) -> Order:
    """Record that the order is fulfilled by an external platform and close KA dispatch."""
    if order.status in (OrderStatus.delivered, OrderStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Order already {order.status.value}")

    _close_internal_dispatch(db, order)

    order.fulfillment_type = "external"
    order.external_provider = provider
    order.external_reference = (reference or "").strip() or None
    order.external_note = (note or "").strip() or None
    order.external_status = "assigned"
    order.external_assigned_at = utcnow()

    audit_service.record(
        db,
        actor_user_id=admin.id,
        action="order_external_assigned",
        target_type="order",
        target_id=order.id,
        order_id=order.id,
        detail=f"provider={provider} ref={order.external_reference or '-'}",
    )
    if not order.is_test:
        notification_service.notify(
            order.customer_id,
            "Delivery arranged",
            f"Order #{order.id} will be delivered via {provider.title()}.",
            {"order_id": order.id, "type": "external_delivery"},
        )
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order


def update_external_status(db: Session, order: Order, admin: User, status: str) -> Order:
    """Advance the manually-tracked status of an externally-fulfilled order."""
    if order.fulfillment_type != "external":
        raise HTTPException(status_code=409, detail="Order is not externally fulfilled")

    order.external_status = status
    if status == "delivered" and order.status not in (
        OrderStatus.delivered,
        OrderStatus.cancelled,
    ):
        # External couriers bypass the internal state machine; record delivery directly.
        order.status = OrderStatus.delivered
        order.delivered_at = utcnow()
        db.add(
            AuditEvent(
                order_id=order.id,
                actor_user_id=admin.id,
                event_type="order_status",
                from_state=None,
                to_state=OrderStatus.delivered.value,
                detail=f"external:{order.external_provider}",
            )
        )
    elif status == "cancelled" and order.status not in (
        OrderStatus.delivered,
        OrderStatus.cancelled,
    ):
        order.status = OrderStatus.cancelled
        order.cancelled_reason = f"external:{order.external_provider} cancelled"

    audit_service.record(
        db,
        actor_user_id=admin.id,
        action="order_external_status",
        target_type="order",
        target_id=order.id,
        order_id=order.id,
        detail=f"status={status}",
    )
    db.commit()
    manager.publish(order.id)
    db.refresh(order)
    return order
