/** Typed admin API client. JWT is kept in memory + localStorage. */
import { config } from '@/config';
import { recordApiCall } from '@/api/api-log';
import type {
  ActiveDelivery,
  AssignOrderPayload,
  CandidateRider,
  DeliveryIssue,
  ExternalDeliveryStatus,
  Me,
  Overview,
  OrderDetail,
  OrderSummary,
  Page,
  PartnerApplication,
  PartnerApplicationDetail,
  PartnerDetail,
  PartnerUpdatePayload,
  PartnerListItem,
  TestDelivery,
  Token,
  WithdrawalRequest,
  WithdrawalSummary,
  WithdrawalDetail,
} from '@/api/types';

const TOKEN_KEY = 'digimess.admin.token';
let authToken: string | null = localStorage.getItem(TOKEN_KEY);

export function setToken(token: string | null): void {
  authToken = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}
export function getToken(): string | null {
  return authToken;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<T> {
  const { method = 'GET', body, auth = true } = options;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth && authToken) headers.Authorization = `Bearer ${authToken}`;
  const started = performance.now();
  const log = (fields: { status: number; ok: boolean; responseBody?: unknown; error?: string }) =>
    recordApiCall({
      method,
      path,
      requestBody: body,
      durationMs: Math.round(performance.now() - started),
      timestamp: Date.now(),
      ...fields,
    });
  let resp: Response;
  try {
    resp = await fetch(`${config.apiUrl}/api/v1${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    log({ status: 0, ok: false, error: 'Network error' });
    throw new ApiError(0, 'Network error — is the backend reachable?');
  }
  if (resp.status === 401) {
    setToken(null);
  }
  if (resp.status === 204) {
    log({ status: 204, ok: true });
    return undefined as T;
  }
  const text = await resp.text();
  const data = text ? safeJson(text) : null;
  log({ status: resp.status, ok: resp.ok, responseBody: data });
  if (!resp.ok) {
    throw new ApiError(resp.status, extractDetail(data) ?? `Request failed (${resp.status})`);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
function extractDetail(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length) return (d[0] as { msg?: string })?.msg ?? 'Validation error';
  }
  return null;
}

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

/** Authenticated document URL (opened in a new tab / <img>). */
export function documentUrl(docId: number): string {
  return `${config.apiUrl}/api/v1/admin/documents/${docId}`;
}

export const api = {
  adminLogin: (email: string, password: string) =>
    request<Token>('/auth/admin/login', { method: 'POST', body: { email, password }, auth: false }),
  me: () => request<Me>('/auth/me'),

  overview: () => request<Overview>('/admin/overview'),

  // Verification
  applications: (status?: string) =>
    request<Page<PartnerApplication>>(`/admin/applications${qs({ status, limit: 200 })}`),
  application: (riderId: number) =>
    request<PartnerApplicationDetail>(`/admin/applications/${riderId}`),
  review: (riderId: number) =>
    request<PartnerApplicationDetail>(`/admin/applications/${riderId}/review`, { method: 'POST' }),
  approve: (riderId: number) =>
    request<PartnerApplicationDetail>(`/admin/applications/${riderId}/approve`, { method: 'POST' }),
  reject: (riderId: number, reason: string) =>
    request<PartnerApplicationDetail>(`/admin/applications/${riderId}/reject`, { method: 'POST', body: { reason } }),
  requestCorrection: (riderId: number, reason: string) =>
    request<PartnerApplicationDetail>(`/admin/applications/${riderId}/request-correction`, { method: 'POST', body: { reason } }),

  // Partners
  partners: (params: { q?: string; status?: string; online?: boolean } = {}) =>
    request<Page<PartnerListItem>>(`/admin/partners${qs({ ...params, limit: 200 })}`),
  partner: (riderId: number) => request<PartnerDetail>(`/admin/partners/${riderId}`),
  updatePartner: (riderId: number, body: PartnerUpdatePayload) =>
    request<PartnerDetail>(`/admin/partners/${riderId}`, { method: 'PATCH', body }),
  addPartnerNote: (riderId: number, note: string) =>
    request<PartnerDetail>(`/admin/partners/${riderId}/notes`, { method: 'POST', body: { reason: note } }),
  suspend: (riderId: number, reason: string) =>
    request<PartnerDetail>(`/admin/partners/${riderId}/suspend`, { method: 'POST', body: { reason } }),
  reactivate: (riderId: number, reason: string) =>
    request<PartnerDetail>(`/admin/partners/${riderId}/reactivate`, { method: 'POST', body: { reason } }),

  // Orders & issues
  orders: (params: { q?: string; status?: string; is_test?: boolean } = {}) =>
    request<Page<OrderSummary>>(`/admin/orders${qs({ ...params, limit: 200 })}`),
  order: (orderId: number) => request<OrderDetail>(`/admin/orders/${orderId}`),
  orderCandidates: (orderId: number) =>
    request<CandidateRider[]>(`/admin/orders/${orderId}/candidate-riders`),
  assignOrder: (orderId: number, body: AssignOrderPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/assign`, { method: 'POST', body }),
  setOrderExternalStatus: (orderId: number, status: ExternalDeliveryStatus) =>
    request<OrderDetail>(`/admin/orders/${orderId}/external-status`, { method: 'POST', body: { status } }),
  issues: (status?: string) => request<Page<DeliveryIssue>>(`/admin/issues${qs({ status, limit: 200 })}`),
  addIssueNote: (issueId: number, note: string) =>
    request<DeliveryIssue>(`/admin/issues/${issueId}/note`, { method: 'POST', body: { note } }),
  resolveIssue: (issueId: number) =>
    request<DeliveryIssue>(`/admin/issues/${issueId}/resolve`, { method: 'POST' }),

  // Operations
  withdrawalsSummary: () => request<WithdrawalSummary>('/admin/withdrawals/summary'),
  withdrawal: (id: number) => request<WithdrawalDetail>(`/admin/withdrawals/${id}`),
  withdrawals: (params: { status?: string; q?: string } = {}) =>
    request<Page<WithdrawalRequest>>(`/admin/withdrawals${qs({ ...params, limit: 200 })}`),
  approveWithdrawal: (id: number) => request<WithdrawalRequest>(`/admin/withdrawals/${id}/approve`, { method: 'POST' }),
  rejectWithdrawal: (id: number, reason: string) =>
    request<WithdrawalRequest>(`/admin/withdrawals/${id}/reject`, { method: 'POST', body: { reason } }),
  bulkApproveWithdrawals: (ids: number[]) =>
    request<{ count: number }>('/admin/withdrawals/bulk-approve', { method: 'POST', body: { ids } }),

  activeDeliveries: (isTest?: boolean) =>
    request<ActiveDelivery[]>(`/admin/deliveries/active${qs({ is_test: isTest })}`),

  // Test-order tool
  testOrders: () => request<Page<TestDelivery>>('/admin/test-orders?limit=200'),
  placeAutocomplete: (input: string) =>
    request<Array<{ place_id: string; label: string; secondary?: string | null }>>(
      '/admin/maps/places/autocomplete',
      { method: 'POST', body: { input } },
    ),
  placeDetails: (placeId: string) =>
    request<{ lat: number; lng: number; label: string; address: string }>(
      `/admin/maps/places/${encodeURIComponent(placeId)}`,
    ),
  createTestOrder: (body: Record<string, unknown>) =>
    request<TestDelivery>('/admin/test-orders', { method: 'POST', body }),
  advanceTestOrder: (orderId: number, to: string) =>
    request<TestDelivery>(`/admin/test-orders/${orderId}/advance${qs({ to })}`, { method: 'POST' }),
  assignTestOrder: (orderId: number, riderId: number) =>
    request<TestDelivery>(`/admin/test-orders/${orderId}/assign`, { method: 'POST', body: { rider_id: riderId } }),
  cancelTestOrder: (orderId: number) =>
    request<TestDelivery>(`/admin/test-orders/${orderId}/cancel`, { method: 'POST' }),
};
