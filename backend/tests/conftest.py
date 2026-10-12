"""Pytest fixtures. A dedicated SQLite file DB is used and reset per test.

DATABASE_URL is set BEFORE importing any app module so the cached settings,
engine and SessionLocal (used by both routes and the WebSocket handler) all
point at the test database.
"""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
# Override backend/.env PostgreSQL vars so tests stay on in-memory SQLite.
os.environ["DATABASE_HOST"] = ""
os.environ["DATABASE_NAME"] = ""
os.environ["DATABASE_USER"] = ""
os.environ["DATABASE_PASSWORD"] = ""
os.environ["DATABASE_URL"] = "sqlite:///./test_digimess.db"
os.environ["JWT_SECRET"] = "test-secret"
# Tighten location policy so tests can exercise jump/speed rejection.
os.environ["LOCATION_MAX_JUMP_METERS"] = "2000"
os.environ["LOCATION_STALE_SECONDS"] = "30"
os.environ["SEED_ACTIVE_DELIVERY"] = "false"
os.environ["SEED_PICKUP_DELIVERY"] = "false"
os.environ["AUTO_MIGRATE_ON_STARTUP"] = "false"
os.environ["AUTO_SEED_ON_STARTUP"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _reset_db() -> None:
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def external_orders(monkeypatch):
    """Serve the external order API from ``tests.helpers.EXTERNAL_ORDERS``.

    Autouse so no test can reach the real network.
    """
    from app.schemas.external_order import ExternalOrder
    from app.services import external_order_client
    from tests import helpers

    helpers.EXTERNAL_ORDERS.clear()

    def fake_fetch(ref: str) -> ExternalOrder:
        payload = helpers.EXTERNAL_ORDERS.get(ref)
        if payload is None:
            raise external_order_client.ExternalOrderNotFound("Order not found")
        if payload == "down":
            raise external_order_client.ExternalOrderError("External order API is unreachable")
        return ExternalOrder.model_validate(payload)

    monkeypatch.setattr(external_order_client, "fetch_order", fake_fetch)
    return helpers.EXTERNAL_ORDERS


@pytest.fixture
def client():
    from app import seed as seed_module
    from app.main import app

    _reset_db()
    seed_module.seed()
    with TestClient(app) as test_client:
        yield test_client


# ---- auth helpers -------------------------------------------------------

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, kind: str, email: str, password: str = "password123") -> str:
    resp = client.post(
        f"/api/v1/auth/{kind}/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def customer_token(client) -> str:
    return login(client, "customer", "customer@digimess.app")


@pytest.fixture
def rider_token(client) -> str:
    return login(client, "rider", "rider@digimess.app")


@pytest.fixture
def mess_token(client) -> str:
    return login(client, "mess", "mess@digimess.app")


@pytest.fixture
def auth():
    return _auth
