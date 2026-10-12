"""Rider location validation and delivery workflow tests."""
from __future__ import annotations

from tests.conftest import _auth, login
from tests.helpers import (
    active_batch,
    drive_to_out_for_delivery,
    mess_advance,
    now_iso,
    place_order,
    rider_online,
)


def test_invalid_location_future_timestamp_rejected(client, rider_token):
    ids = drive_to_out_for_delivery(client, rider_token)
    assert ids
    resp = client.post(
        "/api/v1/rider/location",
        headers=_auth(rider_token),
        json={"lat": 18.52, "lng": 73.85, "client_timestamp": "2099-01-01T00:00:00"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "timestamp_in_future"


def test_implausible_jump_rejected(client, rider_token):
    drive_to_out_for_delivery(client, rider_token)
    resp = client.post(
        "/api/v1/rider/location",
        headers=_auth(rider_token),
        json={"lat": 0.0, "lng": 0.0, "client_timestamp": now_iso(2)},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] in {"implausible_jump", "implausible_speed"}


def test_location_allowed_while_online_without_delivery(client, rider_token):
    client.post("/api/v1/rider/online", headers=_auth(rider_token))
    resp = client.post(
        "/api/v1/rider/location",
        headers=_auth(rider_token),
        json={"lat": 18.52, "lng": 73.85, "client_timestamp": now_iso()},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_rider_cannot_complete_another_riders_delivery(client, rider_token):
    ids = drive_to_out_for_delivery(client, rider_token)
    combo_rider = login(client, "rider", "rider2@digimess.app")
    resp = client.post(
        f"/api/v1/deliveries/{ids['delivery_id']}/complete",
        headers=_auth(combo_rider),
        json={"otp": ids["otp"]},
    )
    assert resp.status_code == 403


def test_complete_requires_correct_otp(client, rider_token):
    ids = drive_to_out_for_delivery(client, rider_token)
    bad = client.post(
        f"/api/v1/deliveries/{ids['delivery_id']}/complete",
        headers=_auth(rider_token),
        json={"otp": "0000000"},
    )
    assert bad.status_code == 400


def test_end_to_end_delivery_and_earnings(client, rider_token):
    ids = drive_to_out_for_delivery(client, rider_token)
    done = client.post(
        f"/api/v1/deliveries/{ids['delivery_id']}/complete",
        headers=_auth(rider_token),
        json={"otp": ids["otp"]},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "delivered"

    earnings = client.get("/api/v1/rider/earnings", headers=_auth(rider_token)).json()
    assert earnings["summary"]["total_deliveries"] == 1
    assert earnings["summary"]["paid_payout_cents"] > 0


def test_dispatch_retries_when_rider_goes_online(client, rider_token):
    resp = client.post("/api/v1/rider/offline", headers=_auth(rider_token))
    assert resp.status_code == 204, resp.text
    combo_token = login(client, "rider", "rider2@digimess.app")
    resp = client.post("/api/v1/rider/offline", headers=_auth(combo_token))
    assert resp.status_code == 204, resp.text

    order = place_order()
    mess_advance(order["id"], "accept")
    mess_advance(order["id"], "prepare")
    mess_advance(order["id"], "ready")

    assert client.get("/api/v1/rider/active", headers=_auth(rider_token)).json() is None
    rider_online(client, rider_token)
    batch = active_batch(client, rider_token)
    assert batch is not None
    assert batch["stops"][0]["order_id"] == order["id"]


def test_rider_auto_assigned_on_mess_accept(client, rider_token):
    rider_online(client, rider_token)
    order = place_order()
    mess_advance(order["id"], "accept")
    batch = active_batch(client, rider_token)
    assert batch is not None
    assert batch["status"] in {"assigned", "picked_up"}
