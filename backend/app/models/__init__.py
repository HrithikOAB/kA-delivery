"""Model package. Importing everything here ensures all tables are registered
on ``Base.metadata`` for Alembic autogeneration and ``create_all``.
"""
from app.models.auth_otp import LoginOtp
from app.models.delivery import Delivery, DeliveryBatch, DeliveryOffer
from app.models.delivery_issue import DeliveryIssue
from app.models.enums import (
    ACTIVE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    AdminRole,
    ApprovalStatus,
    BatchStatus,
    DeliveryIssueStatus,
    DeliveryStatus,
    DocumentStatus,
    OfferStatus,
    OrderStatus,
    PaymentStatus,
    PayoutStatus,
    UserRole,
)
from app.models.mess import Mess, MenuItem
from app.models.order import Order, OrderItem
from app.models.partner_api_key import PartnerApiKey
from app.models.rider_document import RiderDocument
from app.models.support_ticket import SupportTicket
from app.models.support_faq import SupportFaq
from app.models.tracking import AuditEvent, RiderLocation
from app.models.rider_cashout import RiderCashout
from app.models.rider_wallet import RiderWallet
from app.models.wallet_transaction import WalletTransaction
from app.models.rider_incentive import RiderIncentive
from app.models.user import Address, RiderProfile, User

__all__ = [
    "User",
    "RiderCashout",
    "RiderWallet",
    "WalletTransaction",
    "RiderIncentive",
    "RiderProfile",
    "Address",
    "Mess",
    "MenuItem",
    "Order",
    "OrderItem",
    "PartnerApiKey",
    "DeliveryBatch",
    "Delivery",
    "DeliveryOffer",
    "RiderLocation",
    "AuditEvent",
    "RiderDocument",
    "DeliveryIssue",
    "SupportTicket",
    "SupportFaq",
    "LoginOtp",
    "UserRole",
    "AdminRole",
    "ApprovalStatus",
    "DocumentStatus",
    "DeliveryIssueStatus",
    "OrderStatus",
    "DeliveryStatus",
    "BatchStatus",
    "OfferStatus",
    "PaymentStatus",
    "PayoutStatus",
    "ACTIVE_ORDER_STATUSES",
    "TERMINAL_ORDER_STATUSES",
]
