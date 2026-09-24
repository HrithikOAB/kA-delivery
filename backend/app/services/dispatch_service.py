"""Dispatch engine: batch creation and the rider offer loop.

Implements the diagram flow: when an order is ready the dispatch engine puts it
in a delivery batch and offers the batch to an eligible rider; on reject/expiry
the next eligible rider is offered, and on accept the batch is assigned.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import utcnow
from app.models.delivery import Delivery, DeliveryBatch, DeliveryOffer
from app.models.enums import (
    BatchStatus,
    DeliveryStatus,
    OfferStatus,
    OrderStatus,
    UserRole,
)
from app.models.mess import Mess
from app.models.order import Order
from app.models.user import RiderProfile, User
from app.services import notification_service, state_machine
from app.services.eta_service import haversine_km


def ensure_batch_for_ready_order(db: Session, order: Order) -> DeliveryBatch:
    """Attach a ready order to an open batch for its mess (creating one if
    needed) and create the per-order ``Delivery`` row.
    """
    existing = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()
    if existing is not None:
        return db.get(DeliveryBatch, existing.batch_id)

    batch = db.execute(
        select(DeliveryBatch)
        .where(
            DeliveryBatch.mess_id == order.mess_id,
            DeliveryBatch.status == BatchStatus.open,
        )
        .order_by(DeliveryBatch.created_at)
    ).scalars().first()

    if batch is not None:
        current_size = db.execute(
            select(Delivery).where(Delivery.batch_id == batch.id)
        ).scalars().all()
        if len(current_size) >= settings.dispatch_max_batch_size:
            batch = None

    if batch is None:
        batch = DeliveryBatch(mess_id=order.mess_id, status=BatchStatus.open)
        db.add(batch)
        db.flush()

    seq = db.execute(
        select(Delivery).where(Delivery.batch_id == batch.id)
    ).scalars().all()
    delivery = Delivery(
        order_id=order.id,
        batch_id=batch.id,
        status=DeliveryStatus.pending,
        sequence=len(seq),
        earning_cents=_delivery_earning(order),
    )
    db.add(delivery)
    db.flush()
    return batch


def _delivery_earning(order: Order) -> int:
    """Rider earning for a delivery: the delivery fee plus a flat base."""
    base = 1500
    return base + order.delivery_fee_cents


def eligible_riders(db: Session, batch: DeliveryBatch) -> list[tuple[User, float]]:
    """Return approved, online riders not already busy or previously offered
    this batch, sorted by distance to the mess (unknown-distance last).
    """
    mess = db.get(Mess, batch.mess_id)

    already = {
        o.rider_id
        for o in db.execute(
            select(DeliveryOffer).where(DeliveryOffer.batch_id == batch.id)
        ).scalars()
    }

    busy = {
        b.rider_id
        for b in db.execute(
            select(DeliveryBatch).where(
                DeliveryBatch.status.in_(
                    [BatchStatus.assigned, BatchStatus.picked_up]
                )
            )
        ).scalars()
        if b.rider_id is not None
    }

    profiles = db.execute(
        select(RiderProfile).where(RiderProfile.is_online.is_(True))
    ).scalars().all()

    candidates: list[tuple[User, float]] = []
    for profile in profiles:
        if not profile.is_approved:
            continue
        if profile.user_id in already or profile.user_id in busy:
            continue
        user = db.get(User, profile.user_id)
        if user is None or not user.has_role(UserRole.rider):
            continue
        if profile.last_lat is not None and profile.last_lng is not None:
            dist = haversine_km(
                profile.last_lat, profile.last_lng, mess.lat, mess.lng
            )
            if dist > settings.dispatch_max_mess_radius_km:
                continue
        else:
            dist = float("inf")
        candidates.append((user, dist))

    candidates.sort(key=lambda t: t[1])
    return candidates


def _rider_is_assignable(db: Session, rider: User, batch: DeliveryBatch) -> bool:
    """True when the rider can take this batch (online, approved, not busy)."""
    profile = rider.rider_profile
    if profile is None or not profile.is_approved or not profile.is_online:
        return False
    if not rider.has_role(UserRole.rider):
        return False
    busy = db.execute(
        select(DeliveryBatch).where(
            DeliveryBatch.rider_id == rider.id,
            DeliveryBatch.status.in_([BatchStatus.assigned, BatchStatus.picked_up]),
            DeliveryBatch.id != batch.id,
        )
    ).scalar_one_or_none()
    if busy is not None:
        return False
    mess = db.get(Mess, batch.mess_id)
    if (
        profile.last_lat is not None
        and profile.last_lng is not None
        and mess is not None
        and haversine_km(profile.last_lat, profile.last_lng, mess.lat, mess.lng)
        > settings.dispatch_max_mess_radius_km
    ):
        return False
    return True


def resolve_assignable_rider(db: Session, batch: DeliveryBatch) -> User | None:
    """Pick the configured default rider when online, else the nearest eligible rider."""
    default = db.execute(
        select(User).where(User.email == settings.default_rider_email.lower())
    ).scalar_one_or_none()
    if default is not None and _rider_is_assignable(db, default, batch):
        return default
    candidates = eligible_riders(db, batch)
    return candidates[0][0] if candidates else None


def auto_assign_rider(db: Session, batch: DeliveryBatch, order: Order) -> User | None:
    """Immediately assign a rider to the batch (no offer loop).

    Used when the mess accepts an order so a delivery partner is reserved early.
    The order stays in ``accepted`` until the kitchen marks it ready, then moves
    to ``assigned``.
    """
    rider: User | None
    if batch.rider_id is not None:
        rider = db.get(User, batch.rider_id)
    else:
        rider = resolve_assignable_rider(db, batch)
        if rider is None:
            return None
        batch.rider_id = rider.id
        batch.status = BatchStatus.assigned

    if rider is None:
        return None

    for delivery in batch.deliveries:
        delivery.rider_id = rider.id
        if delivery.status in (DeliveryStatus.pending, DeliveryStatus.offered):
            state_machine.transition_delivery(
                db,
                delivery,
                DeliveryStatus.accepted,
                actor_user_id=rider.id,
                detail="auto-assign",
            )
    if batch.status == BatchStatus.open:
        batch.status = BatchStatus.assigned
    db.flush()
    return rider


def assign_order_if_rider_ready(db: Session, order: Order, batch: DeliveryBatch) -> None:
    """When the meal is ready, mark the order assigned if a rider is already reserved."""
    if batch.rider_id is None:
        return
    if order.status == OrderStatus.ready:
        state_machine.transition_order(
            db, order, OrderStatus.assigned, actor_user_id=batch.rider_id
        )


def create_offer(db: Session, batch: DeliveryBatch, rider: User) -> DeliveryOffer:
    """Send ``batch`` to a specific ``rider`` and mark its deliveries offered.

    Shared by the automatic offer loop and the admin manual-assign action.
    Eligibility is the caller's responsibility.
    """
    now = utcnow()
    offer = DeliveryOffer(
        batch_id=batch.id,
        rider_id=rider.id,
        status=OfferStatus.sent,
        sent_at=now,
        # Offer stays open until the rider accepts or rejects (no auto-expire on accept).
        expires_at=now + timedelta(seconds=max(settings.dispatch_offer_timeout_seconds, 86400)),
    )
    db.add(offer)
    batch.status = BatchStatus.offered
    for delivery in batch.deliveries:
        if delivery.status == DeliveryStatus.pending:
            state_machine.transition_delivery(
                db, delivery, DeliveryStatus.offered, detail=f"offer:{rider.id}"
            )
    db.flush()
    return offer


def offer_batch_to_next_rider(db: Session, batch: DeliveryBatch) -> DeliveryOffer | None:
    """Send the batch to the next eligible rider. Returns the offer or None if
    no eligible rider is available.
    """
    candidates = eligible_riders(db, batch)
    if not candidates:
        return None
    return create_offer(db, batch, candidates[0][0])



def offer_still_open(batch: DeliveryBatch | None) -> bool:
    """True while the batch is unassigned and waiting for a rider response."""
    if batch is None:
        return False
    if batch.rider_id is not None:
        return False
    return batch.status in (BatchStatus.offered, BatchStatus.open)


def offer_is_actionable(offer: DeliveryOffer, batch: DeliveryBatch | None) -> bool:
    """Rider can accept/decline while the batch is still unassigned.

    Includes ``expired`` offers that timed out under the old 30s policy but were
    never reassigned — so partners are not blocked after a slow review.
    """
    if not offer_still_open(batch):
        return False
    return offer.status in (OfferStatus.sent, OfferStatus.expired)


def _expire_if_needed(db: Session, offer: DeliveryOffer) -> bool:
    if offer.status == OfferStatus.sent and offer.expires_at < utcnow():
        offer.status = OfferStatus.expired
        offer.responded_at = utcnow()
        return True
    return False


def ensure_missing_deliveries(db: Session) -> int:
    """Create delivery rows for kitchen-accepted orders that never got batched."""
    orders = db.execute(
        select(Order).where(
            Order.status.in_(
                [
                    OrderStatus.accepted,
                    OrderStatus.preparing,
                    OrderStatus.ready,
                ]
            )
        )
    ).scalars().all()
    created = 0
    for order in orders:
        existing = db.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        ).scalar_one_or_none()
        if existing is None:
            ensure_batch_for_ready_order(db, order)
            created += 1
    return created


def repair_assigned_batches(db: Session) -> int:
    """Fix batches that have a rider but stale delivery rows (e.g. after a rejected offer)."""
    batches = db.execute(
        select(DeliveryBatch).where(DeliveryBatch.rider_id.is_not(None))
    ).scalars().all()
    repaired = 0
    for batch in batches:
        rider = db.get(User, batch.rider_id)
        if rider is None:
            continue
        changed = False
        for delivery in batch.deliveries:
            delivery.rider_id = rider.id
            if delivery.status in (DeliveryStatus.pending, DeliveryStatus.offered):
                state_machine.transition_delivery(
                    db,
                    delivery,
                    DeliveryStatus.accepted,
                    actor_user_id=rider.id,
                    detail="repair",
                )
                changed = True
        if batch.status in (BatchStatus.open, BatchStatus.offered):
            batch.status = BatchStatus.assigned
            changed = True
        if changed:
            repaired += 1
    if repaired:
        db.flush()
    return repaired


def retry_pending_dispatches(db: Session) -> int:
    """Re-attempt dispatch for batches stuck without a rider (e.g. kitchen accepted
    while all riders were offline). Returns how many batches were assigned or offered.
    """
    ensure_missing_deliveries(db)
    repair_assigned_batches(db)

    batches = db.execute(
        select(DeliveryBatch).where(
            DeliveryBatch.rider_id.is_(None),
            DeliveryBatch.status == BatchStatus.open,
        )
    ).scalars().all()

    assigned = 0
    for batch in batches:
        if not batch.deliveries:
            continue
        order = db.get(Order, batch.deliveries[0].order_id)
        if order is None:
            continue

        rider = auto_assign_rider(db, batch, order)
        if rider is not None:
            for delivery in batch.deliveries:
                pending_order = db.get(Order, delivery.order_id)
                if pending_order is not None:
                    assign_order_if_rider_ready(db, pending_order, batch)
            assigned += 1
            continue

        if order.status == OrderStatus.ready and offer_batch_to_next_rider(db, batch):
            assigned += 1

    return assigned


def allocate_on_mess_accept(db: Session, order: Order) -> User | None:
    """Create the delivery batch and auto-assign a rider when mess accepts."""
    batch = ensure_batch_for_ready_order(db, order)
    rider = auto_assign_rider(db, batch, order)
    if rider is None:
        return None
    # Test orders never trigger customer-facing notifications.
    if not order.is_test:
        notification_service.notify(
            order.customer_id,
            "Rider assigned",
            f"{rider.full_name} will deliver order #{order.id}.",
            {"order_id": order.id, "type": "rider_assigned"},
        )
        notification_service.notify(
            rider.id,
            "New delivery",
            f"You are assigned to order #{order.id} from {order.mess_id}.",
            {"order_id": order.id, "type": "delivery_assigned"},
        )
    return rider



def prepare_batch_for_pickup(db: Session, batch: DeliveryBatch, rider: User) -> None:
    """Ensure orders and deliveries are in states that allow pickup transitions."""
    if batch.status == BatchStatus.picked_up:
        return
    if batch.status != BatchStatus.assigned:
        raise ValueError("Batch is not ready for pickup")

    for delivery in batch.deliveries:
        delivery.rider_id = rider.id
        order = db.get(Order, delivery.order_id)
        if order is None:
            continue

        if order.status in (OrderStatus.accepted, OrderStatus.preparing):
            raise ValueError(
                f"Order #{order.id} is still being prepared at the mess"
            )
        if order.status == OrderStatus.ready:
            state_machine.transition_order(
                db, order, OrderStatus.assigned, actor_user_id=rider.id
            )
        elif order.status not in (
            OrderStatus.assigned,
            OrderStatus.picked_up,
            OrderStatus.out_for_delivery,
        ):
            raise ValueError(
                f"Order #{order.id} cannot be picked up (status: {order.status.value})"
            )

        if delivery.status in (DeliveryStatus.pending, DeliveryStatus.offered):
            state_machine.transition_delivery(
                db,
                delivery,
                DeliveryStatus.accepted,
                actor_user_id=rider.id,
                detail="pickup-prep",
            )


def finalize_batch_if_done(db: Session, batch: DeliveryBatch) -> bool:
    """Mark batch completed when every delivery stop is delivered."""
    from app.services import earnings_service

    if not batch.deliveries:
        return False
    if not all(d.status == DeliveryStatus.delivered for d in batch.deliveries):
        return False
    if batch.status == BatchStatus.completed:
        return True
    now = utcnow()
    batch.status = BatchStatus.completed
    batch.completed_at = now
    batch.total_earning_cents = earnings_service.reconcile_batch_payout(db, batch.deliveries)
    db.flush()
    return True


def batch_has_pending_deliveries(batch: DeliveryBatch) -> bool:
    return any(d.status != DeliveryStatus.delivered for d in batch.deliveries)


def _open_batch_for_mess(db: Session, mess_id: int) -> DeliveryBatch:
    batch = db.execute(
        select(DeliveryBatch)
        .where(DeliveryBatch.mess_id == mess_id, DeliveryBatch.status == BatchStatus.open)
        .order_by(DeliveryBatch.created_at)
    ).scalars().first()
    if batch is None:
        batch = DeliveryBatch(mess_id=mess_id, status=BatchStatus.open)
        db.add(batch)
        db.flush()
    return batch


def release_delivery_to_dispatch(db: Session, delivery: Delivery) -> None:
    """Return an unstarted/extra stop to the dispatch pool for another rider."""
    order = db.get(Order, delivery.order_id)
    if order is None:
        return
    mess_id = order.mess_id
    open_batch = _open_batch_for_mess(db, mess_id)
    seq = len(db.execute(select(Delivery).where(Delivery.batch_id == open_batch.id)).scalars().all())
    delivery.batch_id = open_batch.id
    delivery.sequence = seq
    delivery.rider_id = None
    if delivery.status not in (DeliveryStatus.delivered, DeliveryStatus.cancelled):
        delivery.status = DeliveryStatus.pending
    if order.status in (OrderStatus.assigned, OrderStatus.picked_up, OrderStatus.out_for_delivery):
        try:
            state_machine.transition_order(db, order, OrderStatus.ready, detail="released-to-pool")
        except state_machine.InvalidTransition:
            order.status = OrderStatus.ready
    db.flush()


def rebalance_rider_active_batch(db: Session, batch: DeliveryBatch) -> DeliveryBatch | None:
    """Keep one in-progress stop per rider; finalize completed portion and release extras."""
    if not batch.deliveries:
        return None

    finalize_batch_if_done(db, batch)
    if not batch_has_pending_deliveries(batch):
        return None

    pending = sorted(
        [d for d in batch.deliveries if d.status != DeliveryStatus.delivered],
        key=lambda d: d.sequence,
    )
    delivered = [d for d in batch.deliveries if d.status == DeliveryStatus.delivered]

    if len(pending) > 1:
        for extra in pending[1:]:
            release_delivery_to_dispatch(db, extra)
        pending = pending[:1]

    keep = pending[0]

    if delivered:
        nb = DeliveryBatch(
            mess_id=batch.mess_id,
            rider_id=batch.rider_id,
            status=BatchStatus.picked_up if keep.status in (DeliveryStatus.picked_up, DeliveryStatus.delivering) else BatchStatus.assigned,
            picked_up_at=batch.picked_up_at,
        )
        db.add(nb)
        db.flush()
        keep.batch_id = nb.id
        keep.sequence = 0
        keep.rider_id = batch.rider_id
        finalize_batch_if_done(db, batch)
        db.flush()
        return nb

    return batch


def close_empty_batch(db: Session, batch: DeliveryBatch) -> None:
    if batch.deliveries:
        return
    batch.rider_id = None
    if batch.status != BatchStatus.completed:
        batch.status = BatchStatus.completed
    db.flush()


def release_remaining_stops_after_completion(db: Session, batch: DeliveryBatch) -> None:
    """After a stop is delivered, return any other pending stops to the dispatch pool."""
    if not batch_has_pending_deliveries(batch):
        finalize_batch_if_done(db, batch)
        return
    for delivery in list(batch.deliveries):
        if delivery.status != DeliveryStatus.delivered:
            release_delivery_to_dispatch(db, delivery)
    finalize_batch_if_done(db, batch)
    db.flush()

def accept_offer(db: Session, offer: DeliveryOffer, rider: User) -> DeliveryBatch:
    if offer.rider_id != rider.id:
        raise PermissionError("Offer does not belong to this rider")
    batch = db.get(DeliveryBatch, offer.batch_id)
    # Idempotent: this rider already holds the batch (e.g. double-tap / retry).
    if batch is not None and batch.rider_id == rider.id:
        return batch
    # Assigned to someone else — give a precise message instead of a generic one.
    if batch is not None and batch.rider_id is not None:
        raise ValueError("This delivery was assigned to another partner")
    if not offer_is_actionable(offer, batch):
        raise ValueError("Offer is no longer available")

    offer.status = OfferStatus.accepted
    offer.responded_at = utcnow()
    batch.rider_id = rider.id
    batch.status = BatchStatus.assigned

    for delivery in batch.deliveries:
        delivery.rider_id = rider.id
        state_machine.transition_delivery(
            db, delivery, DeliveryStatus.accepted, actor_user_id=rider.id
        )
        order = db.get(Order, delivery.order_id)
        if order and order.status == OrderStatus.ready:
            state_machine.transition_order(
                db, order, OrderStatus.assigned, actor_user_id=rider.id
            )
    db.flush()
    return batch


def reject_offer(db: Session, offer: DeliveryOffer, rider: User) -> DeliveryOffer | None:
    if offer.rider_id != rider.id:
        raise PermissionError("Offer does not belong to this rider")
    batch = db.get(DeliveryBatch, offer.batch_id)
    if not offer_is_actionable(offer, batch):
        raise ValueError("Offer is no longer available")
    if offer.status in (OfferStatus.sent, OfferStatus.expired):
        offer.status = OfferStatus.rejected
        offer.responded_at = utcnow()

    batch.status = BatchStatus.open
    for delivery in batch.deliveries:
        if delivery.status == DeliveryStatus.offered:
            delivery.status = DeliveryStatus.pending
    return offer_batch_to_next_rider(db, batch)
