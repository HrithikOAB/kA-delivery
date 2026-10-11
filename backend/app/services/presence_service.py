"""Genuine rider presence.

``RiderProfile.is_online`` is a sticky flag: it is set on ``/rider/online`` and
only cleared on an explicit ``/rider/offline``. A force-closed app therefore
stays "online" forever. This module derives *genuine* presence from a liveness
signal instead — the most recent of ``last_online_at`` and the latest posted
location (the app posts one every few seconds while online). A rider whose last
check-in is older than ``online_heartbeat_timeout_seconds`` is not online.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import utcnow
from app.models.user import RiderProfile
from app.services import location_service


def _timeout() -> timedelta:
    return timedelta(seconds=settings.online_heartbeat_timeout_seconds)


def last_seen_at(db: Session, profile: RiderProfile) -> datetime | None:
    """Most recent liveness signal: going online or posting a location."""
    loc = location_service.latest_location(db, profile.user_id)
    candidates = [
        t
        for t in (profile.last_online_at, loc.server_timestamp if loc else None)
        if t is not None
    ]
    return max(candidates) if candidates else None


def is_effectively_online(
    db: Session, profile: RiderProfile, now: datetime | None = None
) -> bool:
    """True only if flagged online *and* checked in within the heartbeat window."""
    if not profile.is_online:
        return False
    seen = last_seen_at(db, profile)
    if seen is None:
        return False
    now = now or utcnow()
    return (now - seen) <= _timeout()


def sweep_stale_online(db: Session, now: datetime | None = None) -> int:
    """Flip ``is_online`` off for riders whose app has gone silent.

    Called lazily at read time (admin dashboards, dispatch) so the durable flag,
    the online count, and dispatch eligibility all reflect reality. Returns the
    number of riders taken offline.
    """
    now = now or utcnow()
    profiles = db.execute(
        select(RiderProfile).where(RiderProfile.is_online.is_(True))
    ).scalars().all()
    flipped = 0
    for profile in profiles:
        if not is_effectively_online(db, profile, now):
            profile.is_online = False
            flipped += 1
    if flipped:
        db.commit()
    return flipped
