"""Delivery, offer and earnings schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BatchStatus, DeliveryStatus, OfferStatus, OrderStatus


class RiderOrderItemOut(BaseModel):
    name: str
    quantity: int
    line_total_cents: int


class DeliveryStop(BaseModel):
    delivery_id: int
    order_id: int
    status: DeliveryStatus
    order_status: OrderStatus
    sequence: int
    customer_name: str
    address_text: str
    address_lat: float
    address_lng: float
    total_cents: int
    payment_method: str = "cod"
    items: list[RiderOrderItemOut] = []
    prep_ready_in_minutes: int = 0
    address_title: str = ""
    address_subtitle: str = ""
    address_tag: str = ""
    customer_note: str = ""
    customer_phone: str = ""
    customer_verified: bool = False
    eta_minutes: int | None = None
    distance_remaining_km: float | None = None
    route_label: str | None = None
    deliver_by_label: str | None = None
    arrived_at_drop: bool = False
    helper_text: str | None = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    status: OfferStatus
    sent_at: datetime
    expires_at: datetime
    mess_name: str | None = None
    mess_lat: float | None = None
    mess_lng: float | None = None
    order_count: int = 0
    base_earning_cents: int = 0
    surge_cents: int = 0
    incentive_cents: int = 0
    estimated_earning_cents: int = 0
    is_high_demand: bool = False
    stops: list[DeliveryStop] = []


class HotspotOut(BaseModel):
    mess_id: int
    mess_name: str
    lat: float
    lng: float
    demand_level: str
    multiplier: float
    open_batches: int


class IncentiveQuestOut(BaseModel):
    title: str
    target_deliveries: int
    completed_deliveries: int
    bonus_cents: int
    ends_at: str




class OfferOrderSummaryOut(BaseModel):
    item_count: int
    item_tags: list[str] = []
    payment_label: str = "COD"
    is_prepaid: bool = False
    no_cash_collection: bool = False


class OfferDetailOut(OfferOut):
    mess_address: str = ""
    total_distance_km: float = 0.0
    estimated_minutes: int = 0
    route_label: str = ""
    pickup_distance_km: float = 0.0
    drop_distance_km: float = 0.0
    handover_type: str = "doorstep"
    handover_label: str = "Contactless"
    bag_count: int = 1
    bag_size_label: str = "Medium size"
    is_express: bool = False
    payout: PayoutBreakdownOut | None = None
    order_summary: OfferOrderSummaryOut | None = None


class LastCompletedOut(BaseModel):
    mess_name: str
    ticket_ref: str
    item_count: int
    amount_cents: int
    completed_at: str
    completed_ago_label: str = ""


class SurgeHotspotOut(BaseModel):
    title: str
    subtitle: str
    multiplier: float
    distance_km: float
    lat: float
    lng: float
    map_label: str


class DashboardQuestOut(BaseModel):
    title: str
    bonus_cents: int
    progress_pct: int
    completed_deliveries: int
    target_deliveries: int
    remaining: int
    ends_label: str

class RiderDashboardOut(BaseModel):
    hotspots: list[HotspotOut]
    incentive_quest: IncentiveQuestOut
    quest: DashboardQuestOut | None = None
    today_deliveries: int
    today_earnings_cents: int
    earnings_pct_vs_yesterday: float = 0.0
    online_hours_label: str = "—"
    tips_cents: int = 0
    last_completed: LastCompletedOut | None = None
    surge_hotspot: SurgeHotspotOut | None = None


class ActiveDeliveryMetaOut(BaseModel):
    phase: str
    status_label: str
    eta_minutes: int | None = None
    distance_remaining_km: float | None = None
    route_label: str | None = None
    deliver_by_label: str | None = None
    rider_lat: float | None = None
    rider_lng: float | None = None
    arrived_at_drop: bool = False
    helper_text: str | None = None


class BatchOut(BaseModel):
    id: int
    status: BatchStatus
    mess_id: int
    mess_name: str
    mess_lat: float
    mess_lng: float
    picked_up_at: datetime | None = None
    stops: list[DeliveryStop] = []
    active: ActiveDeliveryMetaOut | None = None




class PickupChecklistItemOut(BaseModel):
    key: str
    name: str
    packaging_note: str
    quantity: int
    verified: bool


class PickupTrackingOut(BaseModel):
    eta_minutes: int
    distance_km: float
    route_label: str
    track_status: str
    track_status_label: str
    progress_pct: int


class PickupMerchantOut(BaseModel):
    mess_id: int
    name: str
    address: str
    lat: float
    lng: float
    is_pure_veg: bool
    phone: str
    counter_label: str
    packaging_verified: bool
    food_ready: bool
    pickup_note: str
    image_url: str | None = None


class PickupDetailOut(BaseModel):
    delivery_id: int
    order_id: int
    ticket_ref: str
    phase_label: str
    tracking: PickupTrackingOut
    merchant: PickupMerchantOut
    merchant_pickup_note: str
    checklist: list[PickupChecklistItemOut]
    all_verified: bool
    arrived_at_pickup: bool
    gps_validation_note: str
    rider_lat: float | None = None
    rider_lng: float | None = None
    drop_lat: float = 0.0
    drop_lng: float = 0.0


class PickupVerifyItemsRequest(BaseModel):
    item_keys: list[str]


class PickupVerifyItemsOut(BaseModel):
    ok: bool
    verified_keys: list[str]


class ArrivedAtPickupOut(BaseModel):
    ok: bool
    arrived: bool
    arrived_at: str

class PickupRequest(BaseModel):
    delivery_id: int | None = None  # optional; batch-level pickup by default


class CompleteDeliveryRequest(BaseModel):
    otp: str | None = Field(default=None, max_length=8)


class EarningsSummary(BaseModel):
    total_deliveries: int
    total_earned_cents: int
    today_deliveries: int = 0
    today_earned_cents: int = 0
    pending_payout_cents: int
    paid_payout_cents: int


class EarningLine(BaseModel):
    delivery_id: int
    order_id: int
    amount_cents: int
    payout_status: str
    delivered_at: datetime | None = None


class EarningsResponse(BaseModel):
    summary: EarningsSummary
    lines: list[EarningLine]


class EarningsBucketOut(BaseModel):
    key: str
    label: str
    short: str
    amount_cents: int
    trips: int
    is_today: bool = False


class EarningsWeeklyOut(BaseModel):
    range_label: str
    total_cents: int
    pct_change: float
    trips: int
    online_minutes: int
    online_label: str
    avg_per_delivery_cents: int
    buckets: list[EarningsBucketOut]
    peak: EarningsBucketOut | None = None


class EarningsDailyOut(BaseModel):
    total_cents: int
    trips: int
    online_minutes: int
    online_label: str
    buckets: list[EarningsBucketOut]


class EarningsPayoutOut(BaseModel):
    cycle_label: str
    cycle_subtitle: str
    next_date_label: str
    amount_cents: int
    bank_name: str
    bank_account_masked: str
    bank_verified: bool
    cashout_fee_cents: int


class RiderIncentiveOut(BaseModel):
    id: int
    incentive_type: str
    title: str
    subtitle: str
    target_value: int
    current_value: int
    bonus_cents: int
    status: str
    progress_pct: int
    trips_remaining: int
    ends_at: datetime | None = None


class RecentDailyEarningOut(BaseModel):
    key: str
    title: str
    badge: str
    subtitle: str
    amount_cents: int
    trips: int
    online_label: str
    tip_cents: int
    tag: str | None = None
    icon: str = "weekday"


class EarningsDetailOut(BaseModel):
    view: str
    summary: EarningsSummary
    weekly: EarningsWeeklyOut
    daily: EarningsDailyOut
    payout: EarningsPayoutOut
    incentives: list[RiderIncentiveOut]
    recent_daily: list[RecentDailyEarningOut]
    active_incentive_count: int


class CashoutResultOut(BaseModel):
    ok: bool
    amount_cents: int = 0
    fee_cents: int = 0
    message: str


class PayoutBreakdownOut(BaseModel):
    base_fare_cents: int
    base_fare_label: str
    distance_pay_cents: int
    distance_label: str
    surge_bonus_cents: int
    surge_multiplier: float | None = None
    surge_label: str | None = None
    surge_zone: str | None = None
    tip_cents: int
    tip_customer: str
    total_cents: int


class DeliveryCompletionOut(BaseModel):
    delivery_id: int
    order_id: int
    ticket_ref: str
    status: str
    status_label: str = "DROP-OFF CONFIRMED"
    mess_name: str
    mess_verified: bool
    dropoff_area: str
    address_text: str
    customer_name: str
    total_earned_cents: int
    wallet_credited: bool
    active_minutes: int
    estimated_minutes: int
    minutes_faster: int
    rider_rating: float
    rating_comment: str
    distance_km: float
    payout: PayoutBreakdownOut
    pending_stops: int = 0
    route_timeline: list[dict] = []


class DeliveryHandoverOut(BaseModel):
    delivery_id: int
    order_id: int
    ticket_ref: str
    phase_label: str
    handover_type: str
    handover_type_label: str
    priority_note: str
    instructions: str
    customer_name: str
    address_text: str
    mess_name: str
    otp_verified: bool
    has_photo: bool
    photo_name: str | None = None
    handover_icon: str = "doorstep"
    customer_phone: str = ""


class VerifyOtpResultOut(BaseModel):
    verified: bool
    message: str


class DeliveryPhotoOut(BaseModel):
    has_photo: bool
    photo_name: str | None = None


class ArrivedAtDropOut(BaseModel):
    ok: bool
    arrived: bool
    arrived_at: str
