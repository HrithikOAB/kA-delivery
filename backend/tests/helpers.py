"""Shared flow helpers for driving orders through their lifecycle in tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from tests.conftest import _auth

CUST_LAT, CUST_LNG = 18.5310, 73.8446


def now_iso(offset_seconds: int = 0) -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0)
        + timedelta(seconds=offset_seconds)
    ).isoformat()


def _db_session():
    from app.database import SessionLocal

    return SessionLocal()


# External order API stand-in: ``ORD-<n>`` -> payload, or ``"down"`` to simulate
# an outage. The ``external_orders`` fixture in conftest routes
# ``external_order_client.fetch_order`` here.
EXTERNAL_ORDERS: dict[str, dict | str] = {}
_next_ref = [10000]


def external_payload(
    ref: str,
    *,
    mess_name: str,
    mess_lat: float | None,
    mess_lng: float | None,
    customer_lat: float | None = CUST_LAT,
    customer_lng: float | None = CUST_LNG,
    customer_phone: str = "+919000000001",
    order_status: str = "PLACED",
) -> dict:
    """Shape of the external getRiderOrder ``data`` object."""
    return {
        "customer_details": {
            "customer_id": "CUS-10",
            "name": "Jeevan Thul",
            "location": {"latitude": customer_lat, "longitude": customer_lng},
            "contact_number": customer_phone,
            "address": "Flat 4B, Shivaji Nagar",
            "instruction": "Ring the bell twice",
        },
        "mess_details": {
            "mess_id": "MESS-3",
            "name": mess_name,
            "location": {"latitude": mess_lat, "longitude": mess_lng},
            "contact_number": "9607992777",
            "address": "Padegaon Road, Aurangabad",
        },
        "order_details": {
            "order_id": ref,
            "order_items": [
                {"item_id": "ITEM-3", "name": " Chapati-2 (plate) ", "quantity": 2,
                 "price": 60, "food_type": "Vegetarian"},
                {"item_id": "ITEM-4", "name": "Lassi", "quantity": 1, "price": 40,
                 "food_type": "Vegetarian"},
            ],
            "payment_method": "online",
            "payment_status": "paid",
            "order_status": order_status,
            "currency": "INR",
            "placed_at": "2026-10-07T07:43:03.000Z",
            "item_total": 160,
            "delivery_charge": 20,
            "grand_total": 180,
            "amount_to_collect": 0,
            "partner_order_id": None,
        },
    }


def new_ref() -> str:
    _next_ref[0] += 1
    return f"ORD-{_next_ref[0]}"


def register_external_order(**overrides) -> str:
    """Put an order in the fake external API; return its ref."""
    ref = overrides.pop("ref", None) or new_ref()
    kwargs = {
        "mess_name": overrides.pop("mess_name", "Khana Delivery Kitchen"),
        "mess_lat": overrides.pop("mess_lat", 18.5204),
        "mess_lng": overrides.pop("mess_lng", 73.8567),
    }
    kwargs.update(overrides)
    EXTERNAL_ORDERS[ref] = external_payload(ref, **kwargs)
    return ref


def place_order() -> dict:
    """Register an external order id and cache its content (what assignment does)."""
    from app.models.order import Order
    from app.services import order_hydration_service, partner_order_service

    ref = register_external_order()
    db = _db_session()
    try:
        out = partner_order_service.register_order(db, ref)
        order = db.get(Order, out.internal_id)
        order_hydration_service.hydrate_from_external(db, order)
        db.commit()
        db.refresh(order)
        return {"id": order.id, "ref": ref, "otp_code": order.otp_code}
    finally:
        db.close()


def mess_advance(order_id: int, action: str) -> None:
    """Advance mess workflow via internal services."""
    from app.models.enums import OrderStatus
    from app.models.order import Order
    from app.services import dispatch_service, state_machine

    status_map = {
        "accept": OrderStatus.accepted,
        "prepare": OrderStatus.preparing,
        "ready": OrderStatus.ready,
    }
    db = _db_session()
    try:
        order = db.get(Order, order_id)
        state_machine.transition_order(db, order, status_map[action], actor_user_id=order.mess_id)
        if action == "accept":
            dispatch_service.allocate_on_mess_accept(db, order)
            dispatch_service.repair_assigned_batches(db)
        elif action == "prepare":
            dispatch_service.ensure_missing_deliveries(db)
        elif action == "ready":
            batch = dispatch_service.ensure_batch_for_ready_order(db, order)
            if batch.rider_id is None:
                dispatch_service.offer_batch_to_next_rider(db, batch)
            else:
                dispatch_service.assign_order_if_rider_ready(db, order, batch)
        db.commit()
    finally:
        db.close()


def rider_online(client: TestClient, rtok: str) -> None:
    resp = client.post("/api/v1/rider/online", headers=_auth(rtok))
    assert resp.status_code == 204, resp.text


def accept_first_offer(client: TestClient, rtok: str) -> int:
    offers = client.get("/api/v1/rider/offers", headers=_auth(rtok)).json()
    assert offers, "expected at least one offer"
    offer_id = offers[0]["id"]
    resp = client.post(
        f"/api/v1/deliveries/offers/{offer_id}/accept", headers=_auth(rtok)
    )
    assert resp.status_code == 200, resp.text
    return offer_id


def active_batch(client: TestClient, rtok: str) -> dict:
    resp = client.get("/api/v1/rider/active", headers=_auth(rtok))
    assert resp.status_code == 200, resp.text
    return resp.json()


def drive_to_out_for_delivery(
    client: TestClient, rtok: str
) -> dict:
    """Full path up to (and including) pickup. Returns useful ids."""
    order = place_order()
    order_id = order["id"]
    otp = order["otp_code"]

    rider_online(client, rtok)
    mess_advance(order_id, "accept")
    mess_advance(order_id, "prepare")
    mess_advance(order_id, "ready")

    batch = active_batch(client, rtok)
    if batch is None:
        accept_first_offer(client, rtok)
        batch = active_batch(client, rtok)
    delivery_id = batch["stops"][0]["delivery_id"]

    loc = client.post(
        "/api/v1/rider/location",
        headers=_auth(rtok),
        json={
            "lat": 18.5220,
            "lng": 73.8550,
            "client_timestamp": now_iso(),
        },
    )
    assert loc.status_code == 200, loc.text

    pick = client.post(
        f"/api/v1/deliveries/{delivery_id}/pickup", headers=_auth(rtok)
    )
    assert pick.status_code == 200, pick.text

    return {"order_id": order_id, "delivery_id": delivery_id, "otp": otp}
