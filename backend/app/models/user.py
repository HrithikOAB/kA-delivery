"""User, rider profile and saved address models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, sa_enum
from app.models.enums import AdminRole, ApprovalStatus, UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Email is optional now that customers sign in by phone + OTP; riders and
    # mess owners still register with an email.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Comma-separated list of authorized roles, e.g. "customer" or "customer,rider".
    # Customers self-register; privileged roles are granted, never self-selected.
    roles: Mapped[str] = mapped_column(String(64), default=UserRole.customer.value)

    # Set only for users holding the ``admin`` role; scopes their permissions.
    admin_role: Mapped[AdminRole | None] = mapped_column(
        sa_enum(AdminRole), nullable=True
    )
    # Reason captured when an account is suspended (admin action; audited).
    suspended_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    rider_profile: Mapped["RiderProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def role_list(self) -> list[str]:
        return [r for r in (self.roles or "").split(",") if r]

    def has_role(self, role: UserRole | str) -> bool:
        value = role.value if isinstance(role, UserRole) else role
        return value in self.role_list

    def add_role(self, role: UserRole | str) -> None:
        value = role.value if isinstance(role, UserRole) else role
        if value not in self.role_list:
            current = self.role_list
            current.append(value)
            self.roles = ",".join(current)


class RiderProfile(Base, TimestampMixin):
    __tablename__ = "rider_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    vehicle_type: Mapped[str] = mapped_column(String(32), default="bike")
    vehicle_number: Mapped[str] = mapped_column(String(32))
    license_number: Mapped[str] = mapped_column(String(64))
    emergency_contact: Mapped[str] = mapped_column(String(32), default="")
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        sa_enum(ApprovalStatus), default=ApprovalStatus.submitted
    )
    # Populated when an admin requests corrections; shown to the partner with
    # next steps. Cleared on resubmission.
    correction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_online_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Last known position, denormalised for fast dispatch eligibility checks.
    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    partner_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    # No fabricated values: rating/tier/vehicle metadata/etc. stay NULL until a
    # real value is recorded (a genuine review, an admin/onboarding entry).
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_model: Mapped[str] = mapped_column(String(128), default="")
    vehicle_fuel_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vehicle_cargo_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rc_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    operating_hub: Mapped[str] = mapped_column(String(255), default="")
    fleet_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    surge_priority_pct: Mapped[int | None] = mapped_column(nullable=True)
    bank_name: Mapped[str] = mapped_column(String(64), default="")
    bank_account_masked: Mapped[str] = mapped_column(String(32), default="")
    ifsc_code: Mapped[str] = mapped_column(String(16), default="")
    upi_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    upi_linked: Mapped[bool] = mapped_column(Boolean, default=False)
    app_language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    documents_valid_until: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="rider_profile")

    @property
    def is_approved(self) -> bool:
        return self.approval_status == ApprovalStatus.approved


class Address(Base, TimestampMixin):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(64), default="Home")
    line1: Mapped[str] = mapped_column(String(255))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="addresses")
