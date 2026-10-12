"""Tests for the partner API (order registration + tracking), the live external
order detail, and admin assignment (KA + external)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import _auth, login
from tests.helpers import (
    EXTERNAL_ORDERS,
    drive_to_out_for_delivery,
    now_iso,
    register_external_order,
)

KEY = "secret-key"
H = {"X-API-Key": KEY}


@pytest.fixture
def partner_key():
    from app.config import settings

    settings.integration_api_key = KEY
    yield KEY
    settings.integration_api_key = ""


def admin_token(client, email="admin@kadelivery.app") -> str:
    return login(client, "admin", email)


def _register(client, ref: str) -> dict:
    resp = client.post("/api/v1/partner/orders", json={"order_id": ref}, headers=H)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _online_rider(client) -> str:
    rtok = login(client, "rider", "rider@digimess.app")
    client.post("/api/v1/rider/online", headers=_auth(rtok))
    client.post(
        "/api/v1/rider/location",
        headers=_auth(rtok),
        json={"lat": 18.5210, "lng": 73.8560, "client_timestamp": now_iso()},
    )
    return rtok


def _rahul_id(client, atok: str, order_id: int) -> int:
    cands = client.get(
        f"/api/v1/admin/orders/{order_id}/candidate-riders", headers=_auth(atok)
    ).json()
    return next(c["rider_id"] for c in cands if c["full_name"] == "Rahul Sharma")


# --- Partner API auth -----------------------------------------------------

def test_partner_api_disabled_without_key(client):
    resp = client.post("/api/v1/partner/orders", json={"order_id": "ORD-1"})
    assert resp.status_code == 503


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_partner_api_rejects_missing_or_bad_key(client, partner_key, headers):
    for path in ("/api/v1/partner/orders", "/api/v1/partner/tracking"):
        resp = client.post(path, json={"order_id": "ORD-1"}, headers=headers)
        assert resp.status_code == 401


# --- Registration ---------------------------------------------------------

def test_register_is_idempotent_across_id_formats(client, partner_key):
    r1 = client.post("/api/v1/partner/orders", json={"order_id": "ORD-10001"}, headers=H)
    assert r1.status_code == 201, r1.text
    body = r1.json()
    assert body == {**body, "order_id": "ORD-10001", "status": "placed", "already_existed": False}

    for alt in ({"orderId": 10001}, {"order_id": "10001"}, {"order_id": "ord-10001"}):
        r = client.post("/api/v1/partner/orders", json=alt, headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["already_existed"] is True
        assert r.json()["internal_id"] == body["internal_id"]


@pytest.mark.parametrize("body", [{}, {"order_id": ""}, {"order_id": "BK-12"}])
def test_register_rejects_bad_ids(client, partner_key, body):
    resp = client.post("/api/v1/partner/orders", json=body, headers=H)
    assert resp.status_code == 422


def test_register_stores_only_the_id(client, partner_key):
    from app.database import SessionLocal
    from app.models.order import Order

    out = _register(client, "ORD-77")
    with SessionLocal() as db:
        order = db.get(Order, out["internal_id"])
        assert order.external_order_ref == "ORD-77"
        assert order.source == "partner"
        assert order.mess_id is None and order.customer_id is None
        assert order.address_lat is None and not order.items


# --- Admin list + live detail ---------------------------------------------

def test_admin_list_shows_and_searches_external_ref(client, partner_key):
    _register(client, "ORD-501")
    _register(client, "ORD-502")
    atok = admin_token(client)
    rows = client.get("/api/v1/admin/orders", headers=_auth(atok)).json()["items"]
    assert {"ORD-501", "ORD-502"} <= {r["external_order_ref"] for r in rows}
    hit = client.get("/api/v1/admin/orders", params={"q": "ORD-502"}, headers=_auth(atok)).json()
    assert [r["external_order_ref"] for r in hit["items"]] == ["ORD-502"]


def test_admin_detail_reads_external_api_live(client, partner_key):
    ref = register_external_order(order_status="ACCEPTED", customer_lat=None, customer_lng=None)
    out = _register(client, ref)
    atok = admin_token(client)
    detail = client.get(f"/api/v1/admin/orders/{out['internal_id']}", headers=_auth(atok)).json()

    assert detail["external_error"] is None
    assert detail["external_order_ref"] == ref
    assert detail["external_order_status"] == "ACCEPTED"
    assert detail["subtotal_cents"] == 16000
    assert detail["delivery_fee_cents"] == 2000
    assert detail["total_cents"] == 18000
    assert detail["payment_status"] == "paid"
    assert detail["mess"]["contact_phone"] == "9607992777"
    assert detail["customer"]["name"] == "Jeevan Thul"
    assert detail["customer"]["dropoff_lat"] is None
    assert [i["quantity"] for i in detail["items"]] == [2, 1]
    assert detail["items"][0]["name"] == "Chapati-2 (plate)"
    assert detail["assignment"]["rider_id"] is None


def test_admin_detail_survives_external_outage(client, partner_key):
    out = _register(client, "ORD-900")
    EXTERNAL_ORDERS["ORD-900"] = "down"
    atok = admin_token(client)
    resp = client.get(f"/api/v1/admin/orders/{out['internal_id']}", headers=_auth(atok))
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["external_error"] == "External order API is unreachable"
    assert detail["external_order_ref"] == "ORD-900"
    assert detail["mess"] is None


# --- Candidates + internal assignment -------------------------------------

def test_candidates_use_live_mess_location_before_assignment(client, partner_key):
    _online_rider(client)
    out = _register(client, register_external_order())
    atok = admin_token(client)
    cands = client.get(
        f"/api/v1/admin/orders/{out['internal_id']}/candidate-riders", headers=_auth(atok)
    ).json()
    rahul = next(c for c in cands if c["full_name"] == "Rahul Sharma")
    assert rahul["available"] is True
    assert rahul["distance_km"] is not None


def test_assign_caches_external_content_and_offers(client, partner_key):
    from app.database import SessionLocal
    from app.models.mess import Mess
    from app.models.order import Order

    rtok = _online_rider(client)
    ref = register_external_order(customer_lat=None, customer_lng=None)
    out = _register(client, ref)
    atok = admin_token(client)

    resp = client.post(
        f"/api/v1/admin/orders/{out['internal_id']}/assign",
        headers=_auth(atok),
        json={"mode": "internal", "rider_id": _rahul_id(client, atok, out["internal_id"])},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fulfillment_type"] == "internal"

    with SessionLocal() as db:
        order = db.get(Order, out["internal_id"])
        seeded_mess = db.execute(select(Mess)).scalars().first()
        assert order.mess_id == seeded_mess.id  # matched by name + coordinates
        assert order.customer_phone == "+919000000001"
        assert order.address_text == "Flat 4B, Shivaji Nagar"
        assert order.address_lat is None  # external API had no coordinates
        assert order.total_cents == 18000
        assert len(order.items) == 2
        assert order.otp_code

    offers = client.get("/api/v1/rider/offers", headers=_auth(rtok)).json()
    assert offers, "expected an offer for the assigned rider"


def test_assign_blocked_for_rejected_external_order(client, partner_key):
    _online_rider(client)
    out = _register(client, register_external_order(order_status="REJECTED"))
    atok = admin_token(client)
    rider_id = _rahul_id(client, atok, out["internal_id"])
    resp = client.post(
        f"/api/v1/admin/orders/{out['internal_id']}/assign",
        headers=_auth(atok),
        json={"mode": "internal", "rider_id": rider_id},
    )
    assert resp.status_code == 409
    assert "REJECTED" in resp.json()["detail"]
    detail = client.get(f"/api/v1/admin/orders/{out['internal_id']}", headers=_auth(atok)).json()
    assert detail["external_order_status"] == "REJECTED"
    assert detail["assignment"]["rider_id"] is None


def test_assign_blocked_without_mess_coordinates(client, partner_key):
    from app.database import SessionLocal
    from app.models.user import User

    out = _register(client, register_external_order(mess_lat=None, mess_lng=None))
    atok = admin_token(client)
    with SessionLocal() as db:
        rid = db.execute(select(User.id).where(User.email == "rider@digimess.app")).scalar_one()
    resp = client.post(
        f"/api/v1/admin/orders/{out['internal_id']}/assign",
        headers=_auth(atok),
        json={"mode": "internal", "rider_id": rid},
    )
    assert resp.status_code == 409


def test_assign_unknown_external_order_is_404(client, partner_key):
    out = _register(client, "ORD-404404")  # never put in the fake external API
    atok = admin_token(client)
    cands = client.get(
        f"/api/v1/admin/orders/{out['internal_id']}/candidate-riders", headers=_auth(atok)
    )
    assert cands.status_code == 404


# --- External assignment + status tracking --------------------------------

def test_assign_external_and_mark_delivered(client, partner_key):
    out = _register(client, register_external_order())
    order_id = out["internal_id"]
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


# --- Partner tracking -----------------------------------------------------

def test_tracking_unknown_order_is_404(client, partner_key):
    resp = client.post("/api/v1/partner/tracking", json={"order_id": "ORD-123"}, headers=H)
    assert resp.status_code == 404


def test_tracking_before_assignment(client, partner_key):
    _register(client, "ORD-321")
    resp = client.post("/api/v1/partner/tracking", json={"orderId": 321}, headers=H)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["order_id"] == "ORD-321"
    assert body["status"] == "placed"
    assert body["delivery_status"] is None
    assert body["delivery_partner"] is None
    assert body["location"] is None


def test_tracking_with_partner_and_live_location(client, partner_key):
    rtok = login(client, "rider", "rider@digimess.app")
    ids = drive_to_out_for_delivery(client, rtok)
    from app.database import SessionLocal
    from app.models.order import Order

    with SessionLocal() as db:
        ref = db.get(Order, ids["order_id"]).external_order_ref

    resp = client.post("/api/v1/partner/tracking", json={"order_id": ref}, headers=H)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "out_for_delivery"
    assert body["delivery_status"] in {"picked_up", "delivering"}
    partner = body["delivery_partner"]
    assert partner["name"] == "Rahul Sharma"
    assert partner["phone"]
    assert partner["vehicle_type"]
    loc = body["location"]
    assert loc["lat"] == pytest.approx(18.5220)
    assert loc["lng"] == pytest.approx(73.8550)
    assert loc["is_stale"] is False
    assert body["eta_minutes"] is not None


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
    from app.models.user import User
    from app.services import order_admin_service

    db = SessionLocal()
    try:
        rider = db.execute(
            select(User).where(User.email == "rider@digimess.app")
        ).scalar_one()
        admin = db.execute(
            select(User).where(User.email == "admin@kadelivery.app")
        ).scalar_one()
        from app.core.security import hash_password
        from app.models.enums import UserRole

        customer = User(
            email="test-customer@digimess.app",
            hashed_password=hash_password("password123"),
            full_name="Test Customer",
            roles=UserRole.customer.value,
        )
        db.add(customer)
        db.flush()

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
