"""Mess (kitchen) and menu item models."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Mess(Base, TimestampMixin):
    __tablename__ = "messes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    address_text: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    # No fabricated rating; NULL until the mess earns real reviews. Delivery fee
    # is NULL until the mess owner configures it (treated as 0 at pricing time).
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pickup point created by the admin test-order tool (not a real kitchen).
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_pure_veg: Mapped[bool] = mapped_column(Boolean, default=False)
    pickup_counter_label: Mapped[str] = mapped_column(String(64), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    pickup_note: Mapped[str] = mapped_column(String(512), default="")

    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="mess", cascade="all, delete-orphan"
    )


class MenuItem(Base, TimestampMixin):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    mess_id: Mapped[int] = mapped_column(
        ForeignKey("messes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="Meals")
    price_cents: Mapped[int] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    mess: Mapped[Mess] = relationship(back_populates="menu_items")
