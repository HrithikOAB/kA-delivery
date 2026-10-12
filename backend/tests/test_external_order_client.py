"""Tests for the real external order API client (HTTP layer faked)."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.services import external_order_client
# Bound at import time, before the autouse ``external_orders`` fixture swaps it out.
from app.services.external_order_client import fetch_order as real_fetch_order
from tests.helpers import external_payload


@pytest.fixture
def upstream(monkeypatch):
    """Capture outgoing requests and answer with ``upstream.response``."""

    up = SimpleNamespace(
        calls=[],
        response=httpx.Response(
            200,
            json={
                "success": True,
                "statusCode": 200,
                "data": external_payload(
                    "ORD-1", mess_name="Devgiri Mess", mess_lat=19.895543, mess_lng=75.271412
                ),
            },
        ),
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        up.calls.append({"url": url, "json": json, "headers": headers or {}})
        return up.response

    monkeypatch.setattr(external_order_client.httpx, "post", fake_post)
    return up


def test_no_auth_header_when_key_unset(upstream, monkeypatch):
    monkeypatch.setattr(settings, "external_order_api_key", "")
    order = real_fetch_order("ORD-1")
    assert order.order_details.order_id == "ORD-1"
    assert upstream.calls[0]["json"] == {"order_id": "ORD-1"}
    assert upstream.calls[0]["headers"] == {}


def test_auth_header_sent_when_key_set(upstream, monkeypatch):
    monkeypatch.setattr(settings, "external_order_api_key", "their-secret")
    monkeypatch.setattr(settings, "external_order_api_key_header", "x-api-key")
    real_fetch_order("ORD-1")
    assert upstream.calls[0]["headers"] == {"x-api-key": "their-secret"}


def test_bearer_token_via_authorization_header(upstream, monkeypatch):
    monkeypatch.setattr(settings, "external_order_api_key", "Bearer tok123")
    monkeypatch.setattr(settings, "external_order_api_key_header", "Authorization")
    real_fetch_order("ORD-1")
    assert upstream.calls[0]["headers"] == {"Authorization": "Bearer tok123"}


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credentials_map_to_clear_error(upstream, monkeypatch, status):
    monkeypatch.setattr(settings, "external_order_api_key", "wrong")
    upstream.response = httpx.Response(status, json={"message": "Unauthorized"})
    with pytest.raises(external_order_client.ExternalOrderError) as exc:
        real_fetch_order("ORD-1")
    assert str(exc.value) == "External order API rejected our credentials"
    assert not isinstance(exc.value, external_order_client.ExternalOrderNotFound)


def test_upstream_404_is_not_found(upstream):
    upstream.response = httpx.Response(
        404, json={"success": False, "statusCode": 404, "data": None, "message": "Order not found"}
    )
    with pytest.raises(external_order_client.ExternalOrderNotFound):
        real_fetch_order("ORD-404")
