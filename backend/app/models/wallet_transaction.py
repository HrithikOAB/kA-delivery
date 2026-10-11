"""Wallet ledger entries for riders."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class WalletTransaction(Base, TimestampMixin):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    txn_type: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    reference_number: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(128))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Risk is an assessment output, not a given — NULL until a real check runs.
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payout_cycle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
