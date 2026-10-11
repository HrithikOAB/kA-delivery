"""Shared FastAPI dependencies: auth, current user, and role guards."""
from __future__ import annotations

import secrets

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.enums import AdminRole, ApprovalStatus, UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_ERROR
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR

    sub = payload.get("sub")
    active_role = payload.get("role")
    if sub is None or active_role is None:
        raise _CREDENTIALS_ERROR

    user = db.get(User, int(sub))
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    # The active role in the token must still be one the user is authorized for.
    if active_role not in user.role_list:
        raise _CREDENTIALS_ERROR

    # Stash the active role for role-guarded routes.
    user.active_role = active_role  # type: ignore[attr-defined]
    return user


def require_role(role: UserRole):
    """Dependency factory enforcing that the token's active role matches."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if getattr(user, "active_role", None) != role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {role.value} role",
            )
        return user

    return _guard


def require_approved_rider(user: User = Depends(require_role(UserRole.rider))) -> User:
    profile = user.rider_profile
    if profile is None or profile.approval_status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rider account is not approved yet",
        )
    return user


require_admin = require_role(UserRole.admin)


def require_admin_permission(*allowed: AdminRole):
    """Dependency factory: admin must hold one of ``allowed`` tiers.

    ``super_admin`` implies every permission. Enforced on the backend so the UI
    can never grant capability the token doesn't carry.
    """

    def _guard(user: User = Depends(require_admin)) -> User:
        role = user.admin_role
        if role == AdminRole.super_admin or role in allowed:
            return user
        wanted = ", ".join(a.value for a in allowed) or "a higher"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires {wanted} admin permission",
        )

    return _guard


def require_integration_key(x_api_key: str | None = Header(default=None)) -> None:
    """Server-to-server guard for the booking-app ingestion endpoint.

    Ingestion is disabled (503) until ``INTEGRATION_API_KEY`` is configured, so
    the endpoint is never open by default. The comparison is constant-time.
    """
    expected = settings.integration_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Order ingestion is not configured",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# Convenience singletons.
require_customer = require_role(UserRole.customer)
require_rider = require_role(UserRole.rider)
require_mess = require_role(UserRole.mess)
