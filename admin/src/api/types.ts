/** Types mirroring the backend admin API (see backend/app/schemas/admin.py). */

export type ApprovalStatus =
  | 'draft'
  | 'pending'
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'needs_correction';

export interface Token {
  access_token: string;
  token_type: string;
  role: string;
  roles: string[];
}

export interface Me {
  id: number;
  email: string | null;
  full_name: string;
  phone: string | null;
  roles: string[];
  admin_role: string | null;
}

export interface PartnerApiKey {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
}

/** Only returned by create/rotate; the secret can't be fetched again. */
export interface PartnerApiKeySecret extends PartnerApiKey {
  api_key: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditEvent {
  id: number;
  event_type: string;
  from_state: string | null;
  to_state: string | null;
  actor_user_id: number | null;
  target_type: string | null;
  target_id: number | null;
  reason: string | null;
  detail: string | null;
  created_at: string;
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

export interface PartnerApplication {
  rider_id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  vehicle_type: string;
  vehicle_number: string;
  license_number: string;
  approval_status: ApprovalStatus;
  correction_reason: string | null;
  document_count: number;
  is_online: boolean;
  created_at: string;
}

export interface PartnerApplicationDetail extends PartnerApplication {
  documents: RiderDocument[];
  history: AuditEvent[];
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

export interface OverviewMetrics {
  pending_applications: number;
  approved_partners: number;
  online_partners: number;
  active_deliveries: number;
  unassigned_orders: number;
  delayed_or_issue_deliveries: number;
  orders_today: number;
  gmv_today_cents: number;
  live_kitchen: number;
  live_picked_up: number;
  live_en_route: number;
}

export interface FleetLeader {
  rider_id: number;
  full_name: string;
  total_deliveries: number;
  is_online: boolean;
}

export interface Overview {
  metrics: OverviewMetrics;
  recent_applications: PartnerApplication[];
  recent_issues: DeliveryIssue[];
  fleet_leaders: FleetLeader[];
}

export interface PartnerListItem {
  rider_id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  approval_status: ApprovalStatus;
  is_online: boolean;
  account_active: boolean;
  suspended_reason: string | null;
  current_batch_id: number | null;
  total_deliveries: number;
  partner_code: string | null;
  rating: number | null;
  vehicle_type: string;
  vehicle_model: string;
  vehicle_number: string;
  operating_hub: string;
  wallet_balance_cents: number;
  week_earnings_cents: number;
  payout_pending: boolean;
  active_order_id: number | null;
  last_lat: number | null;
  last_lng: number | null;
  location_updated_at: string | null;
  location_is_stale: boolean;
  last_seen_at: string | null;
}

export interface AdminDeliveryRow {
  delivery_id: number;
  order_id: number;
  status: string;
  order_status: string;
  is_test: boolean;
  earning_cents: number;
  delivered_at: string | null;
  created_at: string;
}

export interface PartnerWalletTxn {
  id: number;
  reference_number: string;
  txn_type: string;
  title: string;
  subtitle: string;
  amount_cents: number;
  status: string;
  created_at: string;
  balance_after_cents: number | null;
}

export interface PartnerActiveOrder {
  order_id: number;
  status: string;
  pickup_label: string;
  dropoff_text: string;
  total_cents: number;
  eta_minutes: number | null;
  progress_step: number;
}

export interface PartnerDeliveryRow extends AdminDeliveryRow {
  mess_name: string | null;
  dropoff_text: string;
  distance_km: number | null;
  total_cents: number;
}

export interface PartnerKycItem { label: string; status: string; ok: boolean }
export interface PartnerAdminNote { id: number; text: string; author_id: number | null; created_at: string }

export interface PartnerDetail extends PartnerListItem {
  license_number: string;
  correction_reason: string | null;
  fleet_tier: string | null;
  bank_name: string;
  bank_account_masked: string;
  upi_linked: boolean;
  phone_verified: boolean;
  rc_status: string | null;
  documents_valid_until: string | null;
  emergency_contact: string;
  contact_email: string | null;
  vehicle_fuel_type: string | null;
  shift_preference: string;
  max_active_orders: number;
  total_earned_cents: number;
  cancel_rate_pct: number;
  tenure_months: number;
  wallet_locked_cents: number;
  wallet_available_cents: number;
  wallet_total_cents: number;
  upi_id: string | null;
  ifsc_code: string;
  daily_cashout_limit_cents: number;
  documents: RiderDocument[];
  kyc_items: PartnerKycItem[];
  wallet_transactions: PartnerWalletTxn[];
  active_order: PartnerActiveOrder | null;
  delivery_history: PartnerDeliveryRow[];
  admin_notes: PartnerAdminNote[];
  recent_deliveries: AdminDeliveryRow[];
  open_issues: DeliveryIssue[];
  history: AuditEvent[];
}

export interface PartnerUpdatePayload {
  full_name?: string;
  phone?: string;
  email?: string;
  emergency_contact?: string;
  operating_hub?: string;
  fleet_tier?: string;
  bank_name?: string;
  bank_account_masked?: string;
  upi_linked?: boolean;
  ifsc_code?: string;
  upi_id?: string;
  vehicle_model?: string;
  vehicle_number?: string;
  license_number?: string;
  vehicle_type?: string;
}

export interface OrderSummary {
  order_id: number;
  external_order_ref: string | null;
  external_order_status: string | null;
  is_test: boolean;
  status: string;
  mess_name: string | null;
  customer_name: string | null;
  rider_name: string | null;
  delivery_status: string | null;
  total_cents: number;
  created_at: string;
  fulfillment_type: string;
  external_provider: string | null;
}

export interface OrderMessInfo {
  mess_id: number | null;
  name: string;
  address_text: string;
  lat: number | null;
  lng: number | null;
  contact_phone: string;
}

export interface OrderCustomerInfo {
  name: string;
  phone: string | null;
  dropoff_text: string;
  dropoff_lat: number | null;
  dropoff_lng: number | null;
  note: string;
}

export interface OrderItemLine {
  name: string;
  unit_price_cents: number;
  quantity: number;
  line_total_cents: number;
  food_type: string | null;
}

export interface OrderAssignment {
  rider_id: number | null;
  rider_name: string | null;
  rider_phone: string | null;
  delivery_status: string | null;
  batch_status: string | null;
  offer_pending: boolean;
  offered_rider_id: number | null;
}

export interface OrderDetail extends OrderSummary {
  dropoff_text: string | null;
  external_error: string | null;
  placed_at: string | null;
  subtotal_cents: number;
  delivery_fee_cents: number;
  tax_cents: number;
  amount_to_collect_cents: number | null;
  currency: string;
  payment_status: string;
  payment_method: string;
  external_reference: string | null;
  external_note: string | null;
  external_status: string | null;
  source: string;
  mess: OrderMessInfo | null;
  customer: OrderCustomerInfo | null;
  items: OrderItemLine[];
  assignment: OrderAssignment | null;
  timeline: AuditEvent[];
  issues: DeliveryIssue[];
}

export interface CandidateRider {
  rider_id: number;
  full_name: string;
  phone: string | null;
  is_online: boolean;
  rating: number | null;
  vehicle_type: string;
  distance_km: number | null;
  location_is_stale: boolean;
  active_order_id: number | null;
  active_mess_id: number | null;
  available: boolean;
  unavailable_reason: string | null;
}

export type ExternalProvider = 'zomato' | 'swiggy' | 'other';
export type ExternalDeliveryStatus = 'assigned' | 'picked_up' | 'delivered' | 'cancelled';

export interface AssignOrderPayload {
  mode: 'internal' | 'external';
  rider_id?: number;
  provider?: ExternalProvider;
  reference?: string;
  note?: string;
}

export interface RiderMarker {
  lat: number;
  lng: number;
  heading: number | null;
  speed: number | null;
  server_timestamp: string;
  is_stale: boolean;
  age_seconds: number;
}

export interface ActiveDelivery {
  order_id: number;
  delivery_id: number | null;
  is_test: boolean;
  order_status: string;
  delivery_status: string | null;
  rider_id: number | null;
  rider_name: string | null;
  pickup_lat: number | null;
  pickup_lng: number | null;
  pickup_label: string | null;
  dropoff_lat: number | null;
  dropoff_lng: number | null;
  dropoff_text: string | null;
  rider_marker: RiderMarker | null;
  eta_minutes: number | null;
  distance_km: number | null;
}


export interface WithdrawalRequest {
  id: number;
  reference_number: string;
  payout_cycle: string;
  created_at: string;
  rider_id: number;
  rider_name: string;
  partner_code: string | null;
  fleet_tier: string;
  rating: number | null;
  amount_cents: number;
  fee_cents: number;
  net_amount_cents: number;
  wallet_balance_cents: number;
  post_cashout_balance_cents: number;
  bank_name: string;
  bank_account_masked: string;
  ifsc_code: string;
  account_holder: string;
  bank_verified: boolean;
  risk_score: number;
  risk_label: string;
  risk_note: string;
  status: 'pending_review' | 'approved' | 'rejected';
  admin_note: string | null;
  requires_dual_signoff: boolean;
  auto_disburse_eligible: boolean;
  reviewed_at: string | null;
}

export interface WithdrawalSummary {
  pending_count: number;
  pending_amount_cents: number;
  approved_today_count: number;
  approved_today_amount_cents: number;
  rejected_count: number;
  rejected_amount_cents: number;
  escrow_reserve_cents: number;
  liquidity_ratio: number;
  total_count: number;
}

export interface WithdrawalDetail extends WithdrawalRequest {
  priority_queue: boolean;
  partner: {
    rider_id: number;
    full_name: string;
    partner_code: string | null;
    operating_hub: string;
    rating: number | null;
    total_deliveries: number;
    active_since: string | null;
    fleet_tier: string;
    phone: string | null;
    kyc_compliance_pct: number;
    kyc_items: { label: string; value: string; ok: boolean }[];
    documents: { doc_type: string; status: string; original_name: string }[];
  };
  wallet: {
    gross_total_cents: number;
    escrow_locked_cents: number;
    available_cashout_cents: number;
    post_withdrawal_cents: number;
    daily_limit_cents: number;
    daily_limit_remaining_cents: number;
    daily_utilization_pct: number;
  };
  bank: {
    bank_name: string;
    branch: string;
    account_masked: string;
    ifsc_code: string;
    account_holder: string;
    penny_drop_verified: boolean;
    name_match_pct: number | null;
  };
  earning_components: {
    reference: string;
    title: string;
    category: string;
    timestamp: string;
    status: string;
    amount_cents: number;
  }[];
  payout_history: {
    reference_number: string;
    created_at: string;
    amount_cents: number;
    mode: string;
    utr: string;
    status: string;
  }[];
  risk: { score: number; label: string; checks: { label: string; ok: boolean }[] };
  reject_reasons: string[];
}
