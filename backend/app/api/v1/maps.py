"""Map utilities proxied through the backend (Directions / Routes API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_rider
from app.models.user import User
from app.schemas.maps import DirectionsOut, LatLngOut
from app.services.maps_service import compute_directions

router = APIRouter(prefix="/maps", tags=["maps"])


@router.get("/directions", response_model=DirectionsOut)
async def directions(
    origin_lat: float = Query(..., ge=-90, le=90),
    origin_lng: float = Query(..., ge=-180, le=180),
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lng: float = Query(..., ge=-180, le=180),
    travel_mode: str = Query("TWO_WHEELER"),
    _: User = Depends(require_rider),
) -> DirectionsOut:
    result = await compute_directions(origin_lat, origin_lng, dest_lat, dest_lng, travel_mode=travel_mode)
    return DirectionsOut(
        points=[LatLngOut(**p) for p in result["points"]],
        distance_meters=result.get("distance_meters"),
        duration_seconds=result.get("duration_seconds"),
        source=result.get("source", "straight"),
    )
