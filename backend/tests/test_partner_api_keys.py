"""Admin-managed partner API keys: issue, use, rotate, revoke, permissions."""
from __future__ import annotations

from tests.conftest import _auth, login

BASE = "/api/v1/admin/api-keys"
TRACK = "/api/v1/partner/tracking"
ORDERS = "/api/v1/partner/orders"


def _super(client) -> str:
    return login(client, "admin", "admin@kadelivery.app")


def _create(client, tok: str, name: str = "Acme Foods") -> dict:
    resp = client.post(BASE, json={"name": name}, headers=_auth(tok))
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_issued_key_unlocks_partner_api_and_is_shown_once(client):
    tok = _super(client)
    assert client.post(ORDERS, json={"order_id": "ORD-1"}).status_code == 503

    key = _create(client, tok)
    assert key["api_key"].startswith("kd_live_")
    assert key["api_key"].startswith(key["key_prefix"])
    assert key["is_active"] is True

    h = {"X-API-Key": key["api_key"]}
    assert client.post(ORDERS, json={"order_id": "ORD-1"}, headers=h).status_code == 201
    assert client.post(TRACK, json={"order_id": "ORD-1"}, headers=h).status_code == 200
    assert client.post(TRACK, json={"order_id": "ORD-1"}, headers={"X-API-Key": "nope"}).status_code == 401

    listed = client.get(BASE, headers=_auth(tok)).json()
    row = next(k for k in listed if k["id"] == key["id"])
    assert "api_key" not in row  # the secret is never returned again
    assert row["last_used_at"] is not None


def test_rotate_invalidates_old_key(client):
    tok = _super(client)
    key = _create(client, tok)
    rotated = client.post(f"{BASE}/{key['id']}/rotate", headers=_auth(tok))
    assert rotated.status_code == 200, rotated.text
    new = rotated.json()
    assert new["api_key"] != key["api_key"]
    assert new["rotated_at"] is not None

    assert client.post(TRACK, json={"order_id": "ORD-1"}, headers={"X-API-Key": key["api_key"]}).status_code == 401
    assert client.post(ORDERS, json={"order_id": "ORD-1"}, headers={"X-API-Key": new["api_key"]}).status_code == 201


def test_revoke_disables_key_and_api(client):
    tok = _super(client)
    key = _create(client, tok)
    revoked = client.post(f"{BASE}/{key['id']}/revoke", headers=_auth(tok))
    assert revoked.status_code == 200 and revoked.json()["is_active"] is False
    # No active keys and no env key left: the partner API is disabled again.
    assert client.post(ORDERS, json={"order_id": "ORD-1"}, headers={"X-API-Key": key["api_key"]}).status_code == 503
    assert client.post(f"{BASE}/{key['id']}/rotate", headers=_auth(tok)).status_code == 409


def test_revoking_one_key_keeps_others_working(client):
    tok = _super(client)
    a = _create(client, tok, "Partner A")
    b = _create(client, tok, "Partner B")
    client.post(f"{BASE}/{a['id']}/revoke", headers=_auth(tok))
    assert client.post(ORDERS, json={"order_id": "ORD-2"}, headers={"X-API-Key": a["api_key"]}).status_code == 401
    assert client.post(ORDERS, json={"order_id": "ORD-2"}, headers={"X-API-Key": b["api_key"]}).status_code == 201


def test_env_key_still_accepted(client):
    from app.config import settings

    settings.integration_api_key = "env-secret"
    try:
        resp = client.post(ORDERS, json={"order_id": "ORD-3"}, headers={"X-API-Key": "env-secret"})
        assert resp.status_code == 201
    finally:
        settings.integration_api_key = ""


def test_only_super_admin_manages_keys(client):
    for email in ("ops@digimess.app", "verifier@digimess.app"):
        tok = login(client, "admin", email)
        assert client.get(BASE, headers=_auth(tok)).status_code == 403
        assert client.post(BASE, json={"name": "x"}, headers=_auth(tok)).status_code == 403
    assert client.get(BASE).status_code == 401


def test_key_actions_are_audited(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.tracking import AuditEvent

    tok = _super(client)
    key = _create(client, tok)
    client.post(f"{BASE}/{key['id']}/rotate", headers=_auth(tok))
    client.post(f"{BASE}/{key['id']}/revoke", headers=_auth(tok))
    with SessionLocal() as db:
        actions = db.execute(
            select(AuditEvent.event_type).where(AuditEvent.target_type == "partner_api_key")
        ).scalars().all()
    assert set(actions) == {
        "partner_api_key_created", "partner_api_key_rotated", "partner_api_key_revoked",
    }
