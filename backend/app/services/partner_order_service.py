"""Partner-facing order registration and tracking.

Partners register an external order id only; order content stays with the
external order API and is cached onto our row when a rider is assigned (see
``order_admin_service.hydrate_from_external``).
"""
from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.user import User
from app.schemas.partner_api import (
    PartnerDeliveryPartner,
    PartnerLocation,
    PartnerOrderOut,
    PartnerTrackingOut,
)
from app.services import tracking_service

_REF_RE = re.compile(r"^(?:ORD-?)?(\d+)$", re.IGNORECASE)


def normalize_ref(raw: str | int) -> str:
    """``"ORD-10001"``, ``"ord10001"``, ``"10001"`` and ``10001`` -> ``"ORD-10001"``."""
    text = str(raw).strip()
    match = _REF_RE.match(text)
    if match is None:
        raise HTTPException(
            status_code=422,
            detail="order_id must look like 'ORD-10001' or be a numeric id",
        )
    return f"ORD-{int(match.group(1))}"


def find_by_ref(db: Session, ref: str) -> Order | None:
    return db.execute(
        select(Order).where(Order.external_order_ref == ref)
    ).scalar_one_or_none()


def register_order(db: Session, raw: str | int) -> PartnerOrderOut:
    ref = normalize_ref(raw)
    order = find_by_ref(db, ref)
    already_existed = order is not None
    if order is None:
        order = Order(
            external_order_ref=ref,
            status=OrderStatus.placed,
            source="partner",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
    return PartnerOrderOut(
        order_id=ref,
        internal_id=order.id,
        status=order.status.value,
        created_at=order.created_at,
        already_existed=already_existed,
    )


def tracking(db: Session, raw: str | int) -> PartnerTrackingOut:
    ref = normalize_ref(raw)
    order = find_by_ref(db, ref)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    snap = tracking_service.build_snapshot(db, order)
    delivery = db.execute(
        select(Delivery).where(Delivery.order_id == order.id)
    ).scalar_one_or_none()

    partner: PartnerDeliveryPartner | None = None
    if delivery is not None and delivery.rider_id is not None:
        rider = db.get(User, delivery.rider_id)
        if rider is not None:
            profile = rider.rider_profile
            partner = PartnerDeliveryPartner(
                name=rider.full_name,
                phone=rider.phone,
                vehicle_type=profile.vehicle_type if profile else None,
                vehicle_number=profile.vehicle_number if profile else None,
                rating=round(float(profile.rating), 2)
                if profile and profile.rating is not None
                else None,
            )

    location: PartnerLocation | None = None
    if snap.rider_location is not None:
        m = snap.rider_location
        location = PartnerLocation(
            lat=m.lat,
            lng=m.lng,
            heading=m.heading,
            speed=m.speed,
            updated_at=m.server_timestamp,
            is_stale=m.is_stale,
            age_seconds=m.age_seconds,
        )

    return PartnerTrackingOut(
        order_id=ref,
        status=order.status.value,
        delivery_status=delivery.status.value if delivery else None,
        updated_at=snap.updated_at,
        delivery_partner=partner,
        location=location,
        eta_minutes=snap.eta_minutes,
        distance_km=snap.distance_km,
    )
