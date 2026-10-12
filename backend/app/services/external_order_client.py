"""Client for the external order API (``getRiderOrder``).

The external platform owns order content (mess, customer, items, money); we
only keep the order reference and delivery state, and read the rest from here.
"""
from __future__ import annotations

import logging

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.external_order import ExternalOrder

logger = logging.getLogger(__name__)


class ExternalOrderError(Exception):
    """The external order API failed or returned something unusable."""


class ExternalOrderNotFound(ExternalOrderError):
    """The external order API does not know this order id."""


def fetch_order(external_ref: str) -> ExternalOrder:
    url = settings.external_order_api_url
    if not url:
        raise ExternalOrderError("External order API is not configured")
    headers: dict[str, str] = {}
    if settings.external_order_api_key:
        headers[settings.external_order_api_key_header] = settings.external_order_api_key
    try:
        resp = httpx.post(
            url,
            json={"order_id": external_ref},
            headers=headers,
            timeout=settings.external_order_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        logger.warning("External order API unreachable for %s: %s", external_ref, exc)
        raise ExternalOrderError("External order API is unreachable") from exc

    if resp.status_code in (401, 403):
        logger.warning(
            "External order API rejected our credentials (%s) for %s",
            resp.status_code, external_ref,
        )
        raise ExternalOrderError("External order API rejected our credentials")

    try:
        body = resp.json()
    except ValueError as exc:
        raise ExternalOrderError(
            f"External order API returned a non-JSON response ({resp.status_code})"
        ) from exc

    if resp.status_code == 404 or body.get("statusCode") == 404:
        raise ExternalOrderNotFound(body.get("message") or "Order not found")
    if resp.status_code >= 400 or not body.get("success") or not body.get("data"):
        raise ExternalOrderError(
            body.get("message") or f"External order API error ({resp.status_code})"
        )

    try:
        return ExternalOrder.model_validate(body["data"])
    except ValidationError as exc:
        logger.warning("Malformed external order payload for %s: %s", external_ref, exc)
        raise ExternalOrderError("External order API returned an unexpected payload") from exc
