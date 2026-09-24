"""Google Routes API helpers (server-side; key never shipped to clients)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def _decode_polyline(polyline: str) -> list[dict[str, float]]:
    coords: list[dict[str, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(polyline)

    while index < length:
        shift = result = 0
        while True:
            b = ord(polyline[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = result = 0
        while True:
            b = ord(polyline[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coords.append({"lat": lat / 1e5, "lng": lng / 1e5})

    return coords


def _straight_line(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    steps: int = 8,
) -> list[dict[str, float]]:
    pts: list[dict[str, float]] = [{"lat": origin_lat, "lng": origin_lng}]
    for i in range(1, steps + 1):
        t = i / (steps + 1)
        pts.append(
            {
                "lat": origin_lat + (dest_lat - origin_lat) * t,
                "lng": origin_lng + (dest_lng - origin_lng) * t,
            }
        )
    pts.append({"lat": dest_lat, "lng": dest_lng})
    return pts


async def compute_directions(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    travel_mode: str = "TWO_WHEELER",
) -> dict[str, Any]:
    """Return decoded route points plus distance/duration metadata."""
    api_key = settings.google_maps_api_key.strip()
    if not api_key:
        points = _straight_line(origin_lat, origin_lng, dest_lat, dest_lng)
        return {
            "points": points,
            "distance_meters": None,
            "duration_seconds": None,
            "source": "straight",
        }

    body = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.polyline.encodedPolyline,routes.distanceMeters,routes.duration",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(ROUTES_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.warning("Google Routes API %s: %s", resp.status_code, resp.text[:300])
            raise RuntimeError("routes api error")
        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            raise RuntimeError("no routes")
        route = routes[0]
        encoded = route.get("polyline", {}).get("encodedPolyline")
        if not encoded:
            raise RuntimeError("missing polyline")
        points = _decode_polyline(encoded)
        duration = route.get("duration")
        duration_seconds = None
        if isinstance(duration, str) and duration.endswith("s"):
            try:
                duration_seconds = int(duration[:-1])
            except ValueError:
                duration_seconds = None
        return {
            "points": points,
            "distance_meters": route.get("distanceMeters"),
            "duration_seconds": duration_seconds,
            "source": "google",
        }
    except Exception:
        logger.exception("Directions lookup failed; using straight-line fallback")
        points = _straight_line(origin_lat, origin_lng, dest_lat, dest_lng)
        return {
            "points": points,
            "distance_meters": None,
            "duration_seconds": None,
            "source": "straight",
        }


PLACES_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"


def _places_api_key() -> str:
    return settings.google_maps_api_key.strip()


async def search_places(query: str) -> list[dict[str, str | None]]:
    api_key = _places_api_key()
    if not api_key:
        return []

    body = {
        "input": query.strip(),
        "includedRegionCodes": ["in"],
        "languageCode": "en",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(PLACES_AUTOCOMPLETE_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.warning("Places autocomplete %s: %s", resp.status_code, resp.text[:300])
            raise RuntimeError(f"Places autocomplete failed ({resp.status_code})")
        data = resp.json()
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Places autocomplete failed")
        raise RuntimeError("Places autocomplete failed") from exc

    out: list[dict[str, str | None]] = []
    for item in data.get("suggestions") or []:
        pred = item.get("placePrediction") or {}
        place_id = pred.get("placeId")
        if not place_id:
            continue
        fmt = pred.get("structuredFormat") or {}
        label = (fmt.get("mainText") or {}).get("text") or (pred.get("text") or {}).get("text") or "Place"
        secondary = (fmt.get("secondaryText") or {}).get("text")
        out.append({"place_id": place_id, "label": label, "secondary": secondary})
    return out


async def get_place_details(place_id: str) -> dict[str, float | str] | None:
    api_key = _places_api_key()
    if not api_key or not place_id.strip():
        return None

    url = f"https://places.googleapis.com/v1/places/{place_id.strip()}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "displayName,formattedAddress,location",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("Places details %s: %s", resp.status_code, resp.text[:300])
            return None
        place = resp.json()
    except Exception:
        logger.exception("Places details failed")
        return None

    loc = place.get("location") or {}
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    if lat is None or lng is None:
        return None

    return {
        "lat": float(lat),
        "lng": float(lng),
        "label": (place.get("displayName") or {}).get("text") or "Selected place",
        "address": place.get("formattedAddress") or "",
    }
