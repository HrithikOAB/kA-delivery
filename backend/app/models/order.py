"""Order and order-item models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, sa_enum
from app.models.enums import OrderStatus, PaymentStatus


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Partner-registered orders start with only ``external_order_ref``; mess,
    # customer and drop-off are filled from the external order API at assignment.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    mess_id: Mapped[int | None] = mapped_column(
        ForeignKey("messes.id", ondelete="CASCADE"), index=True, nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        sa_enum(OrderStatus), default=OrderStatus.placed, index=True
    )

    # Admin-created test orders are flagged unmistakably and kept distinguishable
    # from real customer orders everywhere (filters, reports). Test orders never
    # trigger real payments, customer notifications, or external side effects.
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    test_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Delivery address snapshot (captured at order time; independent of the
    # mutable saved Address row).
    address_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The external API may not supply customer coordinates.
    address_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    address_title: Mapped[str] = mapped_column(String(128), default="")
    address_subtitle: Mapped[str] = mapped_column(String(255), default="")
    address_tag: Mapped[str] = mapped_column(String(64), default="")
    customer_note: Mapped[str] = mapped_column(String(512), default="")
    customer_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Money in integer cents; totals are always computed server-side.
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)

    payment_status: Mapped[PaymentStatus] = mapped_column(
        sa_enum(PaymentStatus), default=PaymentStatus.pending
    )
    payment_method: Mapped[str] = mapped_column(String(24), default="cod")

    # Origin of the order. Real customer orders come from the booking app; the
    # legacy value "customer" covers the in-repo checkout flow and test tool.
    source: Mapped[str] = mapped_column(String(24), default="customer", index=True)
    # Booking-app order id — makes ingestion idempotent (re-POST returns the same
    # order instead of duplicating). Null for orders not created via ingestion.
    external_order_ref: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True, nullable=True
    )
    # Last ``order_status`` seen from the external order API (e.g. REJECTED).
    external_order_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Fulfillment: an in-platform (KA) rider via the dispatch engine, or an
    # external courier (Zomato/Swiggy/other) tracked manually by ops.
    fulfillment_type: Mapped[str] = mapped_column(String(16), default="internal", index=True)
    external_provider: Mapped[str | None] = mapped_column(String(24), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    external_assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Contact captured at order time (booking-app customers are placeholder users).
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # OTP delivery proof.
    otp_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    menu_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True
    )
    name_snapshot: Mapped[str] = mapped_column(String(255))
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    line_total_cents: Mapped[int] = mapped_column(Integer)
    packaging_note: Mapped[str] = mapped_column(String(255), default="")

    order: Mapped[Order] = relationship(back_populates="items")
