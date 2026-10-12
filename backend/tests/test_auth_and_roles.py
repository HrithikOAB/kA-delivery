"""Rider authentication and authorization tests."""
from __future__ import annotations

from tests.conftest import _auth, login


def test_rider_login(client):
    token = login(client, "rider", "rider@digimess.app")
    me = client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert "rider" in me.json()["roles"]


def test_wrong_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/rider/login",
        json={"email": "rider@digimess.app", "password": "nope"},
    )
    assert resp.status_code == 401


def test_customer_cannot_login_as_rider(client):
    resp = client.post(
        "/api/v1/auth/rider/login",
        json={"email": "admin@kadelivery.app", "password": "password123"},
    )
    assert resp.status_code == 401


def test_unapproved_rider_cannot_go_online(client):
    reg = client.post(
        "/api/v1/auth/rider/register",
        json={
            "email": "newrider@digimess.app",
            "password": "password123",
            "full_name": "New Rider",
            "vehicle_number": "MH01XX0001",
            "license_number": "DL-TEST-0001",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    resp = client.post("/api/v1/rider/online", headers=_auth(token))
    assert resp.status_code == 403


def test_rider_register_and_me(client):
    reg = client.post(
        "/api/v1/auth/rider/register",
        json={
            "email": "fleet@digimess.app",
            "password": "password123",
            "full_name": "Fleet Rider",
            "vehicle_number": "MH12AB1234",
            "license_number": "DL-FLEET-01",
        },
    )
    assert reg.status_code == 201
    assert reg.json()["role"] == "rider"
    me = client.get("/api/v1/auth/me", headers=_auth(reg.json()["access_token"]))
    assert me.json()["full_name"] == "Fleet Rider"
