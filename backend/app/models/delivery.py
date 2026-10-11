"""Delivery batch, per-order delivery and rider offer models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, sa_enum
from app.models.enums import (
    BatchStatus,
    DeliveryStatus,
    OfferStatus,
    PayoutStatus,
)


class DeliveryBatch(Base, TimestampMixin):
    """A batch of one-or-more orders from a single mess assigned to one rider.

    Mirrors the diagram: the dispatch engine creates a batch when orders are
    ready, offers it to eligible riders, and the accepting rider delivers each
    order in the batch before it is completed and earnings are reconciled.
    """

    __tablename__ = "delivery_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    mess_id: Mapped[int] = mapped_column(
        ForeignKey("messes.id", ondelete="CASCADE"), index=True
    )
    rider_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[BatchStatus] = mapped_column(
        sa_enum(BatchStatus), default=BatchStatus.open, index=True
    )
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_earning_cents: Mapped[int] = mapped_column(Integer, default=0)

    deliveries: Mapped[list["Delivery"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    offers: Mapped[list["DeliveryOffer"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Delivery(Base, TimestampMixin):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_batches.id", ondelete="CASCADE"), index=True
    )
    rider_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        sa_enum(DeliveryStatus), default=DeliveryStatus.pending, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    earning_cents: Mapped[int] = mapped_column(Integer, default=0)
    tip_cents: Mapped[int] = mapped_column(Integer, default=0)
    surge_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_fare_cents: Mapped[int] = mapped_column(Integer)
    distance_pay_cents: Mapped[int] = mapped_column(Integer, default=0)
    surge_bonus_cents: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rider_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_comment: Mapped[str | None] = mapped_column(String(128), nullable=True)
    handover_type: Mapped[str] = mapped_column(String(48), default="doorstep")
    handover_instructions: Mapped[str] = mapped_column(String(512), default="")
    priority_note: Mapped[str] = mapped_column(String(128), default="")
    delivery_photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    delivery_photo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_remaining_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_label: Mapped[str] = mapped_column(String(32), default="")
    deliver_by_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    arrived_at_drop_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pickup_eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pickup_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    pickup_route_label: Mapped[str] = mapped_column(String(64), default="")
    pickup_track_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pickup_progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    merchant_pickup_note: Mapped[str] = mapped_column(String(512), default="")
    pickup_counter: Mapped[str] = mapped_column(String(64), default="")
    packaging_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    food_ready: Mapped[bool] = mapped_column(Boolean, default=True)
    arrived_at_pickup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_item_keys: Mapped[str] = mapped_column(String(512), default="")
    payout_status: Mapped[PayoutStatus] = mapped_column(
        sa_enum(PayoutStatus), default=PayoutStatus.pending
    )

    batch: Mapped[DeliveryBatch] = relationship(back_populates="deliveries")


class DeliveryOffer(Base):
    __tablename__ = "delivery_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_batches.id", ondelete="CASCADE"), index=True
    )
    rider_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[OfferStatus] = mapped_column(
        sa_enum(OfferStatus), default=OfferStatus.sent, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch: Mapped[DeliveryBatch] = relationship(back_populates="offers")
