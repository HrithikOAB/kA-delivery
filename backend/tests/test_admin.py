"""Tests for admin auth/permissions, partner verification, and admin tracking access."""
from __future__ import annotations

from tests.conftest import _auth, login


def admin_token(client, email="admin@kadelivery.app") -> str:
    return login(client, "admin", email)


# --- Admin auth & permissions --------------------------------------------

def test_admin_login_and_me(client):
    tok = admin_token(client)
    me = client.get("/api/v1/auth/me", headers=_auth(tok)).json()
    assert me["admin_role"] == "super_admin"
    assert "admin" in me["roles"]


def test_non_admin_cannot_use_admin_login(client):
    resp = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "rider@digimess.app", "password": "password123"},
    )
    assert resp.status_code == 401


def test_permission_tiers_enforced(client):
    # operations-tier admin may not touch the verification queue…
    ops = login(client, "admin", "ops@digimess.app")
    assert client.get("/api/v1/admin/applications", headers=_auth(ops)).status_code == 403
    # …and the verification-tier admin may not assign deliveries.
    verifier = login(client, "admin", "verifier@digimess.app")
    body = {"mode": "internal", "rider_id": 1}
    assert client.post("/api/v1/admin/orders/1/assign", headers=_auth(verifier), json=body).status_code == 403


# --- Partner verification -------------------------------------------------

def test_verification_review_approve_gates_online(client):
    verifier = login(client, "admin", "verifier@digimess.app")
    apps = client.get(
        "/api/v1/admin/applications", headers=_auth(verifier), params={"status": "submitted"}
    ).json()
    applicant = next(a for a in apps["items"] if a["email"] == "applicant@digimess.app")
    rid = applicant["rider_id"]

    # Before approval, the applicant cannot go online.
    atok = login(client, "rider", "applicant@digimess.app")
    assert client.post("/api/v1/rider/online", headers=_auth(atok)).status_code == 403

    assert client.post(f"/api/v1/admin/applications/{rid}/review", headers=_auth(verifier)).status_code == 200
    approved = client.post(f"/api/v1/admin/applications/{rid}/approve", headers=_auth(verifier))
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"
    # History records both transitions.
    assert len(approved.json()["history"]) >= 2

    # Now the approved partner can go online.
    assert client.post("/api/v1/rider/online", headers=_auth(atok)).status_code == 204


def test_request_correction_sets_reason_and_partner_can_resubmit(client):
    verifier = login(client, "admin", "verifier@digimess.app")
    apps = client.get(
        "/api/v1/admin/applications", headers=_auth(verifier), params={"status": "submitted"}
    ).json()
    rid = next(a for a in apps["items"] if a["email"] == "applicant@digimess.app")["rider_id"]

    resp = client.post(
        f"/api/v1/admin/applications/{rid}/request-correction",
        headers=_auth(verifier), json={"reason": "Licence photo is blurry"},
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "needs_correction"
    assert resp.json()["correction_reason"] == "Licence photo is blurry"

    # Partner sees the reason and can resubmit.
    atok = login(client, "rider", "applicant@digimess.app")
    v = client.get("/api/v1/rider/verification", headers=_auth(atok)).json()
    assert v["approval_status"] == "needs_correction"
    assert v["correction_reason"] == "Licence photo is blurry"
    re = client.post("/api/v1/rider/resubmit", headers=_auth(atok))
    assert re.status_code == 200 and re.json()["approval_status"] == "submitted"


def test_document_upload_and_admin_can_fetch(client):
    atok = login(client, "rider", "applicant@digimess.app")
    files = {"file": ("licence.png", b"\x89PNG\r\n\x1a\n" + b"0" * 128, "image/png")}
    up = client.post(
        "/api/v1/rider/documents", headers=_auth(atok),
        data={"doc_type": "license"}, files=files,
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    verifier = login(client, "admin", "verifier@digimess.app")
    got = client.get(f"/api/v1/admin/documents/{doc_id}", headers=_auth(verifier))
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/png")


# --- Admin tracking -------------------------------------------------------

def test_admin_active_deliveries_and_tracking(client):
    from tests.helpers import drive_to_out_for_delivery

    rtok = login(client, "rider", "rider@digimess.app")
    ids = drive_to_out_for_delivery(client, rtok)
    admin = admin_token(client)

    active = client.get("/api/v1/admin/deliveries/active", headers=_auth(admin)).json()
    assert any(d["order_id"] == ids["order_id"] for d in active)
    row = next(d for d in active if d["order_id"] == ids["order_id"])
    assert row["rider_marker"] is not None  # a location was posted

    snap = client.get(f"/api/v1/admin/orders/{ids['order_id']}/tracking", headers=_auth(admin))
    assert snap.status_code == 200
    assert snap.json()["order_id"] == ids["order_id"]


def test_suspend_and_reactivate_partner(client):
    admin = admin_token(client)
    partners = client.get("/api/v1/admin/partners", headers=_auth(admin)).json()
    rid = next(p["rider_id"] for p in partners["items"] if p["email"] == "rider@digimess.app")

    s = client.post(f"/api/v1/admin/partners/{rid}/suspend", headers=_auth(admin), json={"reason": "policy"})
    assert s.status_code == 200 and s.json()["account_active"] is False
    # Suspended rider cannot authenticate for actions.
    from app.database import SessionLocal
    from app.models.user import User
    with SessionLocal() as db:
        assert db.get(User, rid).is_active is False

    r = client.post(f"/api/v1/admin/partners/{rid}/reactivate", headers=_auth(admin), json={"reason": "cleared"})
    assert r.status_code == 200 and r.json()["account_active"] is True
