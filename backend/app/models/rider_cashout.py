"""Instant cashout records for riders."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RiderCashout(Base, TimestampMixin):
    __tablename__ = "rider_cashouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    # Fee and status are supplied by the cashout flow, never assumed.
    fee_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
