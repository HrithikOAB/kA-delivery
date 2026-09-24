"""Shared OTP generation and validation.

A fixed ``default_otp`` (e.g. 1212) makes flows testable without an SMS gateway,
but it is a universal-login backdoor — so it is honoured ONLY outside production.
In production ``generate_otp`` returns a random code (deliver it via SMS) and the
bypass is disabled.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from app.config import settings
from app.models.base import utcnow


def _bypass_enabled() -> bool:
    """The fixed default OTP is accepted only in non-production with a code set."""
    return not settings.is_production and bool(settings.default_otp.strip())


def generate_otp() -> str:
    if settings.is_production:
        length = max(settings.otp_length, 4)
        return "".join(str(secrets.randbelow(10)) for _ in range(length))
    return settings.default_otp


def otp_matches(provided: str, expected: str | None) -> bool:
    code = provided.strip()
    if _bypass_enabled() and code == settings.default_otp:
        return True
    return expected is not None and code == expected.strip()


def otp_is_expired(provided: str, expires_at: datetime | None) -> bool:
    """Return True when the OTP is past expiry (dev default OTP never expires)."""
    if _bypass_enabled() and provided.strip() == settings.default_otp:
        return False
    if expires_at is None:
        return False
    return expires_at < utcnow()
