"""Tests for booking-app ingestion and admin order assignment (KA + external)."""
from __future__ import annotations

from sqlalchemy import select

from tests.conftest import _auth, login


def admin_token(client, email="admin@kadelivery.app") -> str:
    return login(client, "admin", email)


def _ingest_body(ref="BK-1001") -> dict:
    return {
        "external_order_ref": ref,
        "mess": {
            "name": "Partner Kitchen A",
            "address_text": "12 MG Road",
            "lat": 18.5204,
            "lng": 73.8567,
            "contact_phone": "+919000012345",
        },
        "customer": {"name": "Ravi Kumar", "phone": "+919111122233"},
        "items": [
            {"name": "Veg Thali", "unit_price_cents": 12000, "quantity": 2},
            {"name": "Lassi", "unit_price_cents": 4000, "quantity": 1},
        ],
        "dropoff": {
            "address_text": "Flat 5, Shivaji Nagar",
            "lat": 18.5310,
            "lng": 73.8446,
            "note": "Ring the bell twice",
        },
        "payment_method": "cod",
        "delivery_fee_cents": 2000,
    }


# --- Ingestion ------------------------------------------------------------

def test_ingestion_disabled_without_key(client):
    resp = client.post("/api/v1/integration/orders", json=_ingest_body())
    assert resp.status_code == 503


def test_ingestion_rejects_bad_key(client):
    from app.config import settings

    settings.integration_api_key = "secret-key"
    try:
        resp = client.post(
            "/api/v1/integration/orders", json=_ingest_body(), headers={"X-API-Key": "wrong"}
        )
        assert resp.status_code == 401
    finally:
        settings.integration_api_key = ""


def test_ingestion_creates_and_is_idempotent(client):
    from app.config import settings

    settings.integration_api_key = "secret-key"
    try:
        h = {"X-API-Key": "secret-key"}
        r1 = client.post("/api/v1/integration/orders", json=_ingest_body(), headers=h)
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["already_existed"] is False
        assert body1["status"] == "placed"

        # Re-post the same reference — same order, no duplicate.
        r2 = client.post("/api/v1/integration/orders", json=_ingest_body(), headers=h)
        assert r2.status_code == 200
        assert r2.json()["already_existed"] is True
        assert r2.json()["order_id"] == body1["order_id"]

        # Admin sees the enriched detail: totals, mess, customer, items.
        atok = admin_token(client)
        detail = client.get(
            f"/api/v1/admin/orders/{body1['order_id']}", headers=_auth(atok)
        ).json()
        assert detail["source"] == "booking_app"
        assert detail["subtotal_cents"] == 12000 * 2 + 4000
        assert detail["mess"]["name"] == "Partner Kitchen A"
        assert detail["customer"]["phone"] == "+919111122233"
        assert len(detail["items"]) == 2
    finally:
        settings.integration_api_key = ""


# --- Candidate riders + internal assignment (offer) -----------------------

def _online_rider(client) -> str:
    rtok = login(client, "rider", "rider@digimess.app")
    client.post("/api/v1/rider/online", headers=_auth(rtok))
    client.post(
        "/api/v1/rider/location",
        headers=_auth(rtok),
        json={"lat": 18.5210, "lng": 73.8560, "client_timestamp": _now()},
    )
    return rtok


def _now() -> str:
    from tests.helpers import now_iso

    return now_iso()


def _seed_real_order() -> int:
    from tests.helpers import place_order

    return place_order()["id"]


def test_candidate_riders_lists_online_partner_available(client):
    _online_rider(client)
    order_id = _seed_real_order()
    atok = admin_token(client)
    cands = client.get(
        f"/api/v1/admin/orders/{order_id}/candidate-riders", headers=_auth(atok)
    ).json()
    assert isinstance(cands, list) and len(cands) >= 1
    rahul = next(c for c in cands if c["full_name"] == "Rahul Sharma")
    assert rahul["is_online"] is True
    assert rahul["available"] is True
    assert rahul["distance_km"] is not None


def test_assign_internal_creates_offer(client):
    rtok = _online_rider(client)
    order_id = _seed_real_order()
    atok = admin_token(client)
    cands = client.get(
        f"/api/v1/admin/orders/{order_id}/candidate-riders", headers=_auth(atok)
    ).json()
    rider_id = next(c["rider_id"] for c in cands if c["full_name"] == "Rahul Sharma")

    resp = client.post(
        f"/api/v1/admin/orders/{order_id}/assign",
        headers=_auth(atok),
        json={"mode": "internal", "rider_id": rider_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fulfillment_type"] == "internal"

    # The rider now has a pending offer they can accept.
    offers = client.get("/api/v1/rider/offers", headers=_auth(rtok)).json()
    assert any(True for _ in offers), "expected an offer for the assigned rider"


# --- External assignment + status tracking --------------------------------

def test_assign_external_and_mark_delivered(client):
    order_id = _seed_real_order()
    atok = admin_token(client)

    resp = client.post(
        f"/api/v1/admin/orders/{order_id}/assign",
        headers=_auth(atok),
        json={"mode": "external", "provider": "zomato", "reference": "ZOM-9", "note": "rush"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fulfillment_type"] == "external"
    assert body["external_provider"] == "zomato"
    assert body["external_status"] == "assigned"

    done = client.post(
        f"/api/v1/admin/orders/{order_id}/external-status",
        headers=_auth(atok),
        json={"status": "delivered"},
    ).json()
    assert done["external_status"] == "delivered"
    assert done["status"] == "delivered"


# --- One-rider-one-mess rule (service level) ------------------------------

def test_stale_online_rider_swept_offline(client):
    """A rider flagged online but silent past the heartbeat window goes offline."""
    from datetime import timedelta

    from app.config import settings
    from app.database import SessionLocal
    from app.models.base import utcnow
    from app.models.user import RiderProfile, User
    from app.services import presence_service

    db = SessionLocal()
    try:
        rider = db.execute(select(User).where(User.email == "rider@digimess.app")).scalar_one()
        profile = db.get(RiderProfile, rider.rider_profile.id)
        profile.is_online = True
        # Last check-in older than the timeout, and no fresh location.
        profile.last_online_at = utcnow() - timedelta(
            seconds=settings.online_heartbeat_timeout_seconds + 60
        )
        db.commit()

        assert presence_service.is_effectively_online(db, profile) is False
        flipped = presence_service.sweep_stale_online(db)
        assert flipped >= 1
        db.refresh(profile)
        assert profile.is_online is False
    finally:
        db.close()


def test_recent_online_rider_stays_online(client):
    from app.database import SessionLocal
    from app.models.base import utcnow
    from app.models.user import RiderProfile, User
    from app.services import presence_service

    db = SessionLocal()
    try:
        rider = db.execute(select(User).where(User.email == "rider@digimess.app")).scalar_one()
        profile = db.get(RiderProfile, rider.rider_profile.id)
        profile.is_online = True
        profile.last_online_at = utcnow()
        db.commit()
        assert presence_service.is_effectively_online(db, profile) is True
        presence_service.sweep_stale_online(db)
        db.refresh(profile)
        assert profile.is_online is True
    finally:
        db.close()


def test_assign_blocked_when_rider_busy_on_another_mess(client):
    """A rider carrying an active order from mess A cannot be assigned mess B."""
    import pytest
    from fastapi import HTTPException

    from app.database import SessionLocal
    from app.models.delivery import Delivery, DeliveryBatch
    from app.models.enums import BatchStatus, DeliveryStatus, OrderStatus
    from app.models.mess import Mess
    from app.models.order import Order
    from app.models.user import RiderProfile, User
    from app.services import order_admin_service

    db = SessionLocal()
    try:
        rider = db.execute(
            select(User).where(User.email == "rider@digimess.app")
        ).scalar_one()
        admin = db.execute(
            select(User).where(User.email == "admin@kadelivery.app")
        ).scalar_one()
        customer = db.execute(
            select(User).where(User.email == "customer@digimess.app")
        ).scalar_one()

        mess_a = Mess(name="Mess A", lat=18.50, lng=73.85, address_text="A")
        mess_b = Mess(name="Mess B", lat=18.60, lng=73.95, address_text="B")
        db.add_all([mess_a, mess_b])
        db.flush()

        # Active order on mess A, assigned to the rider.
        order_a = Order(
            customer_id=customer.id, mess_id=mess_a.id, status=OrderStatus.assigned,
            address_text="drop", address_lat=18.51, address_lng=73.84, total_cents=1000,
        )
        db.add(order_a)
        db.flush()
        batch_a = DeliveryBatch(mess_id=mess_a.id, rider_id=rider.id, status=BatchStatus.assigned)
        db.add(batch_a)
        db.flush()
        db.add(Delivery(
            order_id=order_a.id, batch_id=batch_a.id, rider_id=rider.id,
            status=DeliveryStatus.accepted, sequence=0, base_fare_cents=9000,
        ))

        # New order on mess B.
        order_b = Order(
            customer_id=customer.id, mess_id=mess_b.id, status=OrderStatus.placed,
            address_text="drop2", address_lat=18.52, address_lng=73.83, total_cents=1000,
        )
        db.add(order_b)
        db.commit()
        db.refresh(order_b)

        with pytest.raises(HTTPException) as exc:
            order_admin_service.assign_internal(db, order_b, admin, rider.id)
        assert exc.value.status_code == 409
    finally:
        db.close()
