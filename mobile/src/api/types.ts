/** Types mirroring the delivery-partner API responses. */

export type Role = 'rider';

export interface Token {
  access_token: string;
  token_type: string;
  role: Role;
  roles: Role[];
}

export type ApprovalStatus =
  | 'draft'
  | 'pending'
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'needs_correction';

export interface RiderProfile {
  vehicle_type: string;
  vehicle_number: string;
  license_number: string;
  approval_status: ApprovalStatus;
  correction_reason?: string | null;
  is_online: boolean;
}

export interface RiderDocument {
  id: number;
  doc_type: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  status: string;
  uploaded_at: string;
}

export interface VerificationStatus {
  approval_status: ApprovalStatus;
  correction_reason: string | null;
  can_go_online: boolean;
  documents: RiderDocument[];
  submitted_at: string | null;
  submitted_label: string;
  verified_pct: number;
  steps_completed: number;
  steps_total: number;
  documents_submitted: number;
  documents_expected: number;
  status_headline: string;
  status_subtitle: string;
}

export interface DeliveryIssue {
  id: number;
  delivery_id: number | null;
  order_id: number | null;
  rider_id: number;
  issue_type: string;
  note: string;
  status: string;
  admin_note: string | null;
  created_at: string;
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  phone: string | null;
  roles: Role[];
  rider_profile: RiderProfile | null;
}

export type OrderStatus =
  | 'placed'
  | 'accepted'
  | 'preparing'
  | 'ready'
  | 'assigned'
  | 'picked_up'
  | 'out_for_delivery'
  | 'delivered'
  | 'cancelled';

export interface OfferOrderSummary {
  item_count: number;
  item_tags: string[];
  payment_label: string;
  is_prepaid: boolean;
  no_cash_collection: boolean;
}

export interface OfferDetail extends Offer {
  mess_address?: string;
  total_distance_km?: number;
  estimated_minutes?: number;
  route_label?: string;
  pickup_distance_km?: number;
  drop_distance_km?: number;
  handover_type?: string;
  handover_label?: string;
  bag_count?: number;
  bag_size_label?: string;
  is_express?: boolean;
  payout?: PayoutBreakdown;
  order_summary?: OfferOrderSummary;
}

export interface Offer {
  id: number;
  batch_id: number;
  status: string;
  sent_at: string;
  expires_at: string;
  mess_name: string | null;
  mess_lat: number | null;
  mess_lng: number | null;
  order_count: number;
  base_earning_cents: number;
  surge_cents: number;
  incentive_cents: number;
  estimated_earning_cents: number;
  is_high_demand: boolean;
  stops: DeliveryStop[];
  active?: ActiveDeliveryMeta | null;
}

export interface RiderOrderItem {
  name: string;
  quantity: number;
  line_total_cents: number;
}

export interface ActiveDeliveryMeta {
  phase: string;
  status_label: string;
  eta_minutes: number;
  distance_remaining_km: number;
  route_label: string;
  deliver_by_label: string;
  rider_lat: number | null;
  rider_lng: number | null;
  arrived_at_drop: boolean;
  helper_text: string;
}

export interface DeliveryStop {
  delivery_id: number;
  order_id: number;
  status: string;
  order_status?: string;
  sequence: number;
  customer_name: string;
  address_text: string;
  address_lat: number | null;
  address_lng: number | null;
  total_cents: number;
  payment_method?: string;
  items?: RiderOrderItem[];
  prep_ready_in_minutes?: number;
  address_title?: string;
  address_subtitle?: string;
  address_tag?: string;
  customer_note?: string;
  customer_phone?: string;
  customer_verified?: boolean;
  eta_minutes?: number;
  distance_remaining_km?: number;
  route_label?: string;
  deliver_by_label?: string;
  arrived_at_drop?: boolean;
  helper_text?: string;
}




export interface PickupChecklistItem {
  key: string;
  name: string;
  packaging_note: string;
  quantity: number;
  verified: boolean;
}

export interface PickupTracking {
  eta_minutes: number;
  distance_km: number;
  route_label: string;
  track_status: string;
  track_status_label: string;
  progress_pct: number;
}

export interface PickupMerchant {
  mess_id: number;
  name: string;
  address: string;
  lat: number;
  lng: number;
  is_pure_veg: boolean;
  phone: string;
  counter_label: string;
  packaging_verified: boolean;
  food_ready: boolean;
  pickup_note: string;
  image_url?: string;
}

export interface PickupDetail {
  delivery_id: number;
  order_id: number;
  ticket_ref: string;
  phase_label: string;
  tracking: PickupTracking;
  merchant: PickupMerchant;
  merchant_pickup_note: string;
  checklist: PickupChecklistItem[];
  all_verified: boolean;
  arrived_at_pickup: boolean;
  gps_validation_note: string;
  rider_lat: number | null;
  rider_lng: number | null;
  drop_lat: number | null;
  drop_lng: number | null;
}

export interface DeliveryHandover {
  delivery_id: number;
  order_id: number;
  ticket_ref: string;
  phase_label: string;
  handover_type: string;
  handover_type_label: string;
  priority_note: string;
  instructions: string;
  customer_name: string;
  address_text: string;
  mess_name: string;
  otp_verified: boolean;
  has_photo: boolean;
  photo_name: string | null;
  handover_icon?: string;
  customer_phone?: string;
}

export interface VerifyOtpResult {
  verified: boolean;
  message: string;
}

export interface DeliveryPhotoResult {
  has_photo: boolean;
  photo_name: string | null;
}

export interface PayoutBreakdown {
  base_fare_cents: number;
  base_fare_label: string;
  distance_pay_cents: number;
  distance_label: string;
  surge_bonus_cents: number;
  surge_multiplier: number | null;
  surge_label: string | null;
  surge_zone: string | null;
  tip_cents: number;
  tip_customer: string;
  total_cents: number;
}

export interface DeliveryCompletion {
  delivery_id: number;
  order_id: number;
  ticket_ref: string;
  status: string;
  status_label: string;
  mess_name: string;
  mess_verified: boolean;
  dropoff_area: string;
  address_text: string;
  customer_name: string;
  total_earned_cents: number;
    today_deliveries?: number;
    today_earned_cents?: number;
  wallet_credited: boolean;
  active_minutes: number;
  estimated_minutes: number;
  minutes_faster: number;
  rider_rating: number;
  rating_comment: string;
  distance_km: number;
  payout: PayoutBreakdown;
  pending_stops: number;
  route_timeline?: Array<{ kind: string; title: string; subtitle: string }>;
}

export interface Batch {
  id: number;
  status: string;
  mess_id: number;
  mess_name: string;
  mess_lat: number;
  mess_lng: number;
  picked_up_at: string | null;
  stops: DeliveryStop[];
  active?: ActiveDeliveryMeta | null;
}

export interface EarningsResponse {
  summary: {
    total_deliveries: number;
    total_earned_cents: number;
    today_deliveries?: number;
    today_earned_cents?: number;
    pending_payout_cents: number;
    paid_payout_cents: number;
  };
  lines: {
    delivery_id: number;
    order_id: number;
    amount_cents: number;
    payout_status: string;
    delivered_at: string | null;
  }[];
}


export interface EarningsBucket {
  key: string;
  label: string;
  short: string;
  amount_cents: number;
  trips: number;
  is_today: boolean;
}

export interface EarningsDetailResponse {
  view: 'weekly' | 'daily';
  summary: EarningsResponse['summary'];
  weekly: {
    range_label: string;
    total_cents: number;
    pct_change: number;
    trips: number;
    online_minutes: number;
    online_label: string;
    avg_per_delivery_cents: number;
    buckets: EarningsBucket[];
    peak: EarningsBucket | null;
  };
  daily: {
    total_cents: number;
    trips: number;
    online_minutes: number;
    online_label: string;
    buckets: EarningsBucket[];
  };
  payout: {
    cycle_label: string;
    cycle_subtitle: string;
    next_date_label: string;
    amount_cents: number;
    bank_name: string;
    bank_account_masked: string;
    bank_verified: boolean;
    cashout_fee_cents: number;
  };
  incentives: {
    id: number;
    incentive_type: string;
    title: string;
    subtitle: string;
    target_value: number;
    current_value: number;
    bonus_cents: number;
    status: string;
    progress_pct: number;
    trips_remaining: number;
    ends_at: string | null;
  }[];
  recent_daily: {
    key: string;
    title: string;
    badge: string;
    subtitle: string;
    amount_cents: number;
    trips: number;
    online_label: string;
    tip_cents: number;
    tag: string | null;
    icon: string;
  }[];
  active_incentive_count: number;
}

export interface CashoutResult {
  ok: boolean;
  amount_cents: number;
  fee_cents: number;
  message: string;
}

export interface Hotspot {
  mess_id: number;
  mess_name: string;
  lat: number;
  lng: number;
  demand_level: string;
  multiplier: number;
  open_batches: number;
}

export interface IncentiveQuest {
  title: string;
  target_deliveries: number;
  completed_deliveries: number;
  bonus_cents: number;
  ends_at: string;
}

export interface DashboardQuest {
  title: string;
  bonus_cents: number;
  progress_pct: number;
  completed_deliveries: number;
  target_deliveries: number;
  remaining: number;
  ends_label: string;
}

export interface LastCompleted {
  mess_name: string;
  ticket_ref: string;
  item_count: number;
  amount_cents: number;
  completed_at: string;
  completed_ago_label: string;
}

export interface SurgeHotspot {
  title: string;
  subtitle: string;
  multiplier: number;
  distance_km: number;
  lat: number;
  lng: number;
  map_label: string;
}

export interface RiderDashboard {
  hotspots: Hotspot[];
  incentive_quest: IncentiveQuest;
  quest?: DashboardQuest | null;
  today_deliveries: number;
  today_earnings_cents: number;
  earnings_pct_vs_yesterday?: number;
  online_hours_label?: string;
  tips_cents?: number;
  last_completed?: LastCompleted | null;
  surge_hotspot?: SurgeHotspot | null;
}



export type WalletTxnFilter = 'all' | 'withdrawals' | 'earnings' | 'incentives';

export interface WalletPayoutAccount {
  id: string;
  type: string;
  label: string;
  account_masked: string;
  holder_name: string;
  verified: boolean;
  is_primary: boolean;
  eta_label: string;
  icon: string;
}

export interface WalletDetails {
  total_balance_cents: number;
  locked_balance_cents: number;
  available_balance_cents: number;
  instant_payout_active: boolean;
  updated_label: string;
  bank: {
    bank_name: string;
    account_masked: string;
    verified: boolean;
    label: string;
  };
  processing_withdrawal: {
    amount_cents: number;
    reference_number: string;
    bank_label: string;
    eta_label: string;
    status: string;
  } | null;
  quick_amounts_cents: number[];
  cashout_fee_cents: number;
  payout_accounts: WalletPayoutAccount[];
  min_withdraw_cents: number;
}

export interface WalletTransaction {
  id: number;
  txn_type: string;
  icon: string;
  title: string;
  subtitle: string;
  amount_cents: number;
  status: string;
  status_label: string;
  reference_number: string;
  time_label: string;
  order_id: number | null;
}

export interface WalletTransactionsResponse {
  filter: WalletTxnFilter;
  count: number;
  items: WalletTransaction[];
}

export interface WalletWithdrawResult {
  ok: boolean;
  amount_cents: number;
  fee_cents: number;
  reference_number: string;
  message: string;
  eta_label: string;
}

export type HistoryPeriod = 'today' | 'yesterday' | 'this_week' | 'this_month' | 'all';
export type HistoryStatus = 'completed' | 'cancelled';

export interface DeliveryHistoryItem {
  delivery_id: number;
  order_id: number;
  ticket_ref: string;
  status: HistoryStatus;
  status_label: string;
  mess_name: string;
  dropoff_area: string;
  completed_at: string | null;
  time_label: string;
  distance_km: number | null;
  amount_cents: number;
  tip_cents: number;
  surge_multiplier: number | null;
  has_surge: boolean;
}

export interface DeliveryHistoryResponse {
  period: HistoryPeriod;
  period_label: string;
  status: HistoryStatus;
  summary: {
    completed_count: number;
    cancelled_count: number;
    total_earned_cents: number;
    today_deliveries?: number;
    today_earned_cents?: number;
  };
  items: DeliveryHistoryItem[];
}

export interface SupportTopic {
  key: string;
  label: string;
}

export interface SupportCategory {
  key: string;
  label: string;
  icon: string;
  topics: SupportTopic[];
}

export interface SupportAgentDesk {
  is_live: boolean;
  agent_name: string;
  avg_wait_minutes: number;
}

export interface SupportFaq {
  id: number;
  category: string;
  question: string;
  answer: string;
}

export interface SupportTicket {
  id: number;
  ticket_number: string;
  category: string;
  topic: string;
  title: string;
  message: string;
  order_id: number | null;
  status: string;
  status_label: string;
  has_attachment: boolean;
  attachment_name: string | null;
  subtitle: string;
  created_at: string;
}

export interface SupportHelp {
  sos_hotline: string;
  agent_desk: SupportAgentDesk;
  categories: SupportCategory[];
  faqs: SupportFaq[];
  ongoing_tickets: SupportTicket[];
  active_ticket_count: number;
}

export interface OtpRequestResponse {
  sent: boolean;
  dev_code?: string | null;
}


export interface RiderProfileDetail {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  partner_code: string;
  rating: number;
  trip_count: number;
  is_online: boolean;
  approval_status: ApprovalStatus;
  phone_verified: boolean;
  operating_hub: string;
  fleet_tier: string;
  surge_priority_pct: number;
  vehicle_type: string;
  vehicle_type_label: string;
  vehicle_model: string;
  vehicle_number: string;
  vehicle_fuel_type: string;
  vehicle_cargo_type: string;
  rc_status: string;
  rc_status_label: string;
  bank_name: string;
  bank_account_masked: string;
  bank_summary: string;
  upi_linked: boolean;
  app_language: string;
  documents_summary: string;
  documents_verified_count: number;
  documents_total_count: number;
  documents_valid_until: string;
}
