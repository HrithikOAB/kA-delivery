"""Test-only live-tracking simulator.

Drives the REAL location pipeline for every online rider: generates smooth,
plausible GPS movement and calls ``location_service.validate_and_store`` on a
fixed interval, exactly as the mobile app's broadcaster would. The admin Live
Tracking map (which polls ``partners?online=true`` every 5s) then shows each
partner moving live — no physical devices required.

Run on the backend host:

    cd backend
    python simulate_partner_tracking.py                       # wander near each rider's last point
    python simulate_partner_tracking.py --center 19.0971,72.8935 --radius-km 3
    python simulate_partner_tracking.py --interval 5 --speed 8

Stop with Ctrl-C. This only writes rider location fixes; it does not touch
orders, offers, or online status. Intended for demos/QA, never production data.
"""
from __future__ import annotations

import argparse
import math
import random
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import RiderProfile
from app.services import location_service

DEFAULT_CENTER = (18.5204, 73.8567)  # Pune; overridable via --center


def _meters_to_deg(dlat_m: float, dlng_m: float, lat: float) -> tuple[float, float]:
    dlat = dlat_m / 111_320.0
    dlng = dlng_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return dlat, dlng


class RiderWalker:
    """Smoothly wanders a rider around a center within a radius."""

    def __init__(self, user_id: int, lat: float, lng: float, center: tuple[float, float], radius_km: float):
        self.user_id = user_id
        self.lat = lat
        self.lng = lng
        self.center = center
        self.radius_m = radius_km * 1000.0
        self.heading = random.uniform(0, 2 * math.pi)

    def _dist_from_center_m(self) -> float:
        dlat_m = (self.lat - self.center[0]) * 111_320.0
        dlng_m = (self.lng - self.center[1]) * 111_320.0 * math.cos(math.radians(self.lat))
        return math.hypot(dlat_m, dlng_m)

    def step(self, speed_mps: float, interval_s: float) -> tuple[float, float, float, float]:
        # Turn back toward center if we've wandered too far, else drift slightly.
        if self._dist_from_center_m() > self.radius_m:
            self.heading = math.atan2(self.center[0] - self.lat, self.center[1] - self.lng)
        else:
            self.heading += random.uniform(-0.4, 0.4)

        dist_m = speed_mps * interval_s
        dnorth = dist_m * math.sin(self.heading)
        deast = dist_m * math.cos(self.heading)
        dlat, dlng = _meters_to_deg(dnorth, deast, self.lat)
        self.lat += dlat
        self.lng += dlng
        heading_deg = (math.degrees(self.heading)) % 360
        return self.lat, self.lng, heading_deg, speed_mps


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate live partner GPS for online riders.")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between fixes (default 5)")
    parser.add_argument("--speed", type=float, default=8.0, help="Rider speed m/s (default 8 ≈ 29 km/h)")
    parser.add_argument("--center", type=str, default=None, help="lat,lng anchor (default: each rider's last point, else Pune)")
    parser.add_argument("--radius-km", type=float, default=3.0, help="Wander radius from center (default 3)")
    args = parser.parse_args()

    center_override: tuple[float, float] | None = None
    if args.center:
        parts = args.center.split(",")
        center_override = (float(parts[0]), float(parts[1]))

    with SessionLocal() as db:
        profiles = db.execute(
            select(RiderProfile).where(RiderProfile.is_online.is_(True))
        ).scalars().all()

    if not profiles:
        print("No online riders found. Set a partner online first, then re-run.")
        return

    walkers: list[RiderWalker] = []
    for p in profiles:
        anchor = center_override or (
            (p.last_lat, p.last_lng) if p.last_lat is not None and p.last_lng is not None else DEFAULT_CENTER
        )
        # Spread starting points a little so partners don't overlap.
        jitter_lat = anchor[0] + random.uniform(-0.01, 0.01)
        jitter_lng = anchor[1] + random.uniform(-0.01, 0.01)
        walkers.append(RiderWalker(p.user_id, jitter_lat, jitter_lng, anchor, args.radius_km))

    print(f"Simulating {len(walkers)} online rider(s) every {args.interval}s. Ctrl-C to stop.")
    try:
        while True:
            with SessionLocal() as db:
                for w in walkers:
                    lat, lng, heading, speed = w.step(args.speed, args.interval)
                    result = location_service.validate_and_store(
                        db,
                        w.user_id,
                        None,
                        lat=lat,
                        lng=lng,
                        client_timestamp=datetime.now(timezone.utc),
                        accuracy=8.0,
                        heading=heading,
                        speed=speed,
                    )
                    if not result.accepted:
                        print(f"  rider {w.user_id}: rejected ({result.reason})")
                db.commit()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] pushed {len(walkers)} fix(es)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
