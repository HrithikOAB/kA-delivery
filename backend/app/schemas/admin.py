"""Admin dashboard request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApprovalStatus
from app.schemas.partner import DeliveryIssueOut, RiderDocumentOut

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard paginated list envelope for admin list endpoints."""

    items: list[T]
    total: int
    limit: int
    offset: int


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    from_state: str | None = None
    to_state: str | None = None
    actor_user_id: int | None = None
    target_type: str | None = None
    target_id: int | None = None
    reason: str | None = None
    detail: str | None = None
    created_at: datetime


class PartnerApplicationOut(BaseModel):
    """A partner in the verification queue / list."""

    rider_id: int
    full_name: str
    email: str | None
    phone: str | None
    vehicle_type: str
    vehicle_number: str
    license_number: str
    approval_status: ApprovalStatus
    correction_reason: str | None
    document_count: int
    is_online: bool
    created_at: datetime


class PartnerApplicationDetail(PartnerApplicationOut):
    documents: list[RiderDocumentOut] = []
    history: list[AuditEventOut] = []


# --- Overview -------------------------------------------------------------

class FleetLeaderOut(BaseModel):
    rider_id: int
    full_name: str
    total_deliveries: int
    is_online: bool


class OverviewMetrics(BaseModel):
    pending_applications: int
    approved_partners: int
    online_partners: int
    active_deliveries: int
    unassigned_orders: int
    delayed_or_issue_deliveries: int
    orders_today: int = 0
    gmv_today_cents: int = 0
    live_kitchen: int = 0
    live_picked_up: int = 0
    live_en_route: int = 0


class OverviewOut(BaseModel):
    metrics: OverviewMetrics
    recent_applications: list["PartnerApplicationOut"] = []
    recent_issues: list["DeliveryIssueOut"] = []
    fleet_leaders: list[FleetLeaderOut] = []


# --- Partner management ---------------------------------------------------

class PartnerListItem(BaseModel):
    rider_id: int
    full_name: str
    email: str | None
    phone: str | None
    approval_status: ApprovalStatus
    is_online: bool
    account_active: bool
    suspended_reason: str | None = None
    current_batch_id: int | None = None
    total_deliveries: int = 0
    partner_code: str | None = None
    rating: float | None = None
    vehicle_type: str = ""
    vehicle_model: str = ""
    vehicle_number: str = ""
    operating_hub: str = ""
    wallet_balance_cents: int = 0
    week_earnings_cents: int = 0
    payout_pending: bool = False
    active_order_id: int | None = None
    last_lat: float | None = None
    last_lng: float | None = None
    location_updated_at: datetime | None = None
    location_is_stale: bool = True
    last_seen_at: datetime | None = None


class AdminDeliveryRow(BaseModel):
    delivery_id: int
    order_id: int
    status: str
    order_status: str
    is_test: bool
    earning_cents: int
    delivered_at: datetime | None = None
    created_at: datetime


class PartnerWalletTxnOut(BaseModel):
    id: int
    reference_number: str
    txn_type: str
    title: str
    subtitle: str = ""
    amount_cents: int
    status: str
    created_at: datetime
    balance_after_cents: int | None = None


class PartnerActiveOrderOut(BaseModel):
    order_id: int
    status: str
    pickup_label: str
    dropoff_text: str | None = None
    total_cents: int
    eta_minutes: float | None = None
    progress_step: int = 0


class PartnerDeliveryRowOut(AdminDeliveryRow):
    mess_name: str | None = None
    dropoff_text: str = ""
    distance_km: float | None = None
    total_cents: int = 0


class PartnerKycItemOut(BaseModel):
    label: str
    status: str
    ok: bool


class PartnerAdminNoteOut(BaseModel):
    id: int
    text: str
    author_id: int | None = None
    created_at: datetime


class PartnerUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    emergency_contact: str | None = None
    operating_hub: str | None = None
    fleet_tier: str | None = None
    bank_name: str | None = None
    bank_account_masked: str | None = None
    upi_linked: bool | None = None
    ifsc_code: str | None = None
    upi_id: str | None = None
    vehicle_model: str | None = None
    vehicle_number: str | None = None
    license_number: str | None = None
    vehicle_type: str | None = None


class PartnerDetail(PartnerListItem):
    license_number: str
    correction_reason: str | None = None
    fleet_tier: str | None = None
    bank_name: str = ""
    bank_account_masked: str = ""
    upi_linked: bool = False
    phone_verified: bool = False
    rc_status: str | None = None
    documents_valid_until: str | None = None
    emergency_contact: str = ""
    contact_email: str | None = None
    vehicle_fuel_type: str | None = None
    shift_preference: str = "Flexible"
    max_active_orders: int = 2
    total_earned_cents: int = 0
    cancel_rate_pct: float = 0.0
    tenure_months: int = 0
    wallet_locked_cents: int = 0
    wallet_available_cents: int = 0
    wallet_total_cents: int = 0
    upi_id: str | None = None
    ifsc_code: str = ""
    daily_cashout_limit_cents: int = 5_000_000
    documents: list[RiderDocumentOut] = []
    kyc_items: list[PartnerKycItemOut] = []
    wallet_transactions: list[PartnerWalletTxnOut] = []
    active_order: PartnerActiveOrderOut | None = None
    delivery_history: list[PartnerDeliveryRowOut] = []
    admin_notes: list[PartnerAdminNoteOut] = []
    recent_deliveries: list[AdminDeliveryRow] = []
    open_issues: list["DeliveryIssueOut"] = []
    history: list[AuditEventOut] = []


# --- Orders & issues ------------------------------------------------------

class OrderSummaryOut(BaseModel):
    order_id: int
    # External platform order id (e.g. "ORD-10001") for partner-registered orders.
    external_order_ref: str | None = None
    external_order_status: str | None = None
    is_test: bool
    status: str
    mess_name: str | None
    customer_name: str | None
    rider_name: str | None
    delivery_status: str | None
    total_cents: int
    created_at: datetime
    fulfillment_type: str = "internal"
    external_provider: str | None = None


class OrderMessInfo(BaseModel):
    # Null when the mess comes live from the external API and is not cached yet.
    mess_id: int | None = None
    name: str
    address_text: str
    lat: float | None = None
    lng: float | None = None
    contact_phone: str = ""


class OrderCustomerInfo(BaseModel):
    name: str
    phone: str | None = None
    dropoff_text: str = ""
    dropoff_lat: float | None = None
    dropoff_lng: float | None = None
    note: str = ""


class OrderItemLine(BaseModel):
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    food_type: str | None = None


class OrderAssignment(BaseModel):
    """Current delivery assignment state for an order."""

    rider_id: int | None = None
    rider_name: str | None = None
    rider_phone: str | None = None
    delivery_status: str | None = None
    batch_status: str | None = None
    offer_pending: bool = False
    offered_rider_id: int | None = None


class OrderDetailOut(OrderSummaryOut):
    dropoff_text: str | None = None
    # Set when the external order API could not be read; the rest of the
    # payload then falls back to whatever is stored locally.
    external_error: str | None = None
    placed_at: str | None = None
    # Money breakdown.
    subtotal_cents: int = 0
    delivery_fee_cents: int = 0
    tax_cents: int = 0
    amount_to_collect_cents: int | None = None
    currency: str = "INR"
    payment_status: str = "pending"
    payment_method: str = "cod"
    # Fulfillment / external courier.
    external_reference: str | None = None
    external_note: str | None = None
    external_status: str | None = None
    source: str = "customer"
    # Nested detail.
    mess: OrderMessInfo | None = None
    customer: OrderCustomerInfo | None = None
    items: list[OrderItemLine] = []
    assignment: OrderAssignment | None = None
    timeline: list[AuditEventOut] = []
    issues: list["DeliveryIssueOut"] = []


class CandidateRiderOut(BaseModel):
    rider_id: int
    full_name: str
    phone: str | None = None
    is_online: bool
    rating: float | None = None
    vehicle_type: str = ""
    distance_km: float | None = None
    location_is_stale: bool = True
    active_order_id: int | None = None
    active_mess_id: int | None = None
    # False when the rider is busy with an order from a *different* mess.
    available: bool = True
    unavailable_reason: str | None = None


class AssignOrderRequest(BaseModel):
    mode: str = Field(pattern="^(internal|external)$")
    # internal
    rider_id: int | None = None
    # external
    provider: str | None = Field(default=None, pattern="^(zomato|swiggy|other)$")
    reference: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=512)


class ExternalStatusRequest(BaseModel):
    status: str = Field(pattern="^(assigned|picked_up|delivered|cancelled)$")


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


# --- Operations map -------------------------------------------------------

class RiderMarkerOut(BaseModel):
    lat: float
    lng: float
    heading: float | None = None
    speed: float | None = None
    server_timestamp: datetime
    is_stale: bool
    age_seconds: float


class ActiveDeliveryOut(BaseModel):
    order_id: int
    delivery_id: int | None
    is_test: bool
    order_status: str
    delivery_status: str | None
    rider_id: int | None
    rider_name: str | None
    pickup_lat: float | None
    pickup_lng: float | None
    pickup_label: str | None
    dropoff_lat: float | None
    dropoff_lng: float | None
    dropoff_text: str | None
    rider_marker: RiderMarkerOut | None = None
    eta_minutes: float | None = None
    distance_km: float | None = None


# --- Withdrawals ----------------------------------------------------------

class WithdrawalRequestOut(BaseModel):
    id: int
    reference_number: str
    payout_cycle: str
    created_at: datetime
    rider_id: int
    rider_name: str
    partner_code: str | None = None
    fleet_tier: str = ""
    rating: float | None = None
    amount_cents: int
    fee_cents: int = 0
    net_amount_cents: int
    wallet_balance_cents: int
    post_cashout_balance_cents: int
    bank_name: str
    bank_account_masked: str
    ifsc_code: str
    account_holder: str
    bank_verified: bool = False
    risk_score: int
    risk_label: str
    risk_note: str
    status: str
    admin_note: str | None = None
    requires_dual_signoff: bool = False
    auto_disburse_eligible: bool = True
    reviewed_at: datetime | None = None


class WithdrawalSummaryOut(BaseModel):
    pending_count: int
    pending_amount_cents: int
    approved_today_count: int
    approved_today_amount_cents: int
    rejected_count: int
    rejected_amount_cents: int
    escrow_reserve_cents: int
    liquidity_ratio: float
    total_count: int


class BulkWithdrawalApproveRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class WithdrawalKycItemOut(BaseModel):
    label: str
    value: str
    ok: bool


class WithdrawalPartnerOut(BaseModel):
    rider_id: int
    full_name: str
    partner_code: str | None = None
    operating_hub: str = ""
    rating: float | None = None
    total_deliveries: int = 0
    active_since: datetime | None = None
    fleet_tier: str = ""
    phone: str | None = None
    kyc_compliance_pct: int = 0
    kyc_items: list[WithdrawalKycItemOut] = []
    documents: list[dict] = []


class WithdrawalWalletOut(BaseModel):
    gross_total_cents: int
    escrow_locked_cents: int
    available_cashout_cents: int
    post_withdrawal_cents: int
    daily_limit_cents: int
    daily_limit_remaining_cents: int
    daily_utilization_pct: float


class WithdrawalBankOut(BaseModel):
    bank_name: str
    branch: str
    account_masked: str
    ifsc_code: str
    account_holder: str
    penny_drop_verified: bool
    name_match_pct: int | None = None


class WithdrawalEarningLineOut(BaseModel):
    reference: str
    title: str
    category: str
    timestamp: datetime
    status: str
    amount_cents: int


class WithdrawalPayoutHistoryOut(BaseModel):
    reference_number: str
    created_at: datetime
    amount_cents: int
    mode: str
    utr: str
    status: str


class WithdrawalRiskCheckOut(BaseModel):
    label: str
    ok: bool


class WithdrawalRiskOut(BaseModel):
    score: int
    label: str
    checks: list[WithdrawalRiskCheckOut]


class WithdrawalDetailOut(WithdrawalRequestOut):
    priority_queue: bool
    partner: WithdrawalPartnerOut
    wallet: WithdrawalWalletOut
    bank: WithdrawalBankOut
    earning_components: list[WithdrawalEarningLineOut]
    payout_history: list[WithdrawalPayoutHistoryOut]
    risk: WithdrawalRiskOut
    reject_reasons: list[str]
