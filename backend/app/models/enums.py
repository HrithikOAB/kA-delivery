"""Domain enums shared across models, schemas and services."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    customer = "customer"
    rider = "rider"
    mess = "mess"
    admin = "admin"


class AdminRole(str, enum.Enum):
    """Backend-enforced admin permission tiers.

    ``super_admin`` implies every other permission; the remaining tiers scope an
    admin to a functional area (see ``api/deps.require_admin_permission``).
    """

    super_admin = "super_admin"
    partner_verification = "partner_verification"
    operations = "operations"
    support = "support"


class ApprovalStatus(str, enum.Enum):
    # Full partner-verification lifecycle. ``pending`` is retained for
    # backward compatibility with rows created before the workflow expanded.
    draft = "draft"
    pending = "pending"
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    needs_correction = "needs_correction"


class DocumentStatus(str, enum.Enum):
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"


class DeliveryIssueStatus(str, enum.Enum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class OrderStatus(str, enum.Enum):
    placed = "placed"
    accepted = "accepted"
    preparing = "preparing"
    ready = "ready"
    assigned = "assigned"
    picked_up = "picked_up"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    offered = "offered"
    accepted = "accepted"
    en_route_to_mess = "en_route_to_mess"
    picked_up = "picked_up"
    delivering = "delivering"
    delivered = "delivered"
    cancelled = "cancelled"


class BatchStatus(str, enum.Enum):
    open = "open"
    offered = "offered"
    assigned = "assigned"
    picked_up = "picked_up"
    completed = "completed"
    cancelled = "cancelled"


class OfferStatus(str, enum.Enum):
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class FulfillmentType(str, enum.Enum):
    """Who delivers an order: an in-platform (KA) rider or an external courier."""

    internal = "internal"
    external = "external"


class ExternalProvider(str, enum.Enum):
    """External delivery platform an order may be handed off to."""

    zomato = "zomato"
    swiggy = "swiggy"
    other = "other"


class ExternalDeliveryStatus(str, enum.Enum):
    """Manually-tracked status of an order fulfilled by an external platform."""

    assigned = "assigned"
    picked_up = "picked_up"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderSource(str, enum.Enum):
    """Where an order originated."""

    customer = "customer"
    booking_app = "booking_app"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class PayoutStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"


# Order status values that mean an order is still "trackable" / live.
ACTIVE_ORDER_STATUSES = {
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.assigned,
    OrderStatus.picked_up,
    OrderStatus.out_for_delivery,
}

TERMINAL_ORDER_STATUSES = {OrderStatus.delivered, OrderStatus.cancelled}
