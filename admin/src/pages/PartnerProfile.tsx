import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { AdminDeliveryRow, PartnerDeliveryRow, PartnerDetail, PartnerUpdatePayload } from '@/api/types';
import { formatGmv, money } from '@/theme';
import { AsyncView, ReasonModal } from '@/ui/kit';

type Tab = 'overview' | 'active' | 'history' | 'bank' | 'wallet';
type WalletFilter = 'all' | 'credits' | 'withdrawals' | 'bonuses';
type ActionModal = 'suspend' | 'reactivate' | null;

function tabList(partner: PartnerDetail) {
  const activeCount = partner.active_order ? 1 : 0;
  return [
    { id: 'overview' as Tab, label: 'Overview & KYC' },
    { id: 'active' as Tab, label: `Active Orders (${activeCount})` },
    { id: 'history' as Tab, label: `Delivery History (${partner.total_deliveries})` },
    { id: 'bank' as Tab, label: 'Bank & Payout Details' },
    { id: 'wallet' as Tab, label: 'Wallet Ledger' },
  ];
}

const ORDER_STEPS = ['Order Accepted', 'Picked Up', 'In Transit', 'Drop'];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}

function partnerId(p: PartnerDetail) {
  return p.partner_code ?? `DM-${String(p.rider_id).padStart(4, '0')}`;
}

function fmt(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function filterWalletTxns(txns: PartnerDetail['wallet_transactions'], filter: WalletFilter) {
  if (filter === 'all') return txns;
  if (filter === 'withdrawals') return txns.filter((t) => ['withdrawal', 'weekly_payout'].includes(t.txn_type));
  if (filter === 'bonuses') return txns.filter((t) => t.txn_type === 'incentive');
  return txns.filter((t) => t.txn_type === 'order_earning' || (t.amount_cents > 0 && !['withdrawal', 'weekly_payout', 'incentive'].includes(t.txn_type)));
}

function txnStatusPill(status: string) {
  if (status === 'completed') return <span className="pp-status-success">Success</span>;
  if (status === 'processing') return <span className="pp-status-warn">Processing</span>;
  return <span className="pp-status-warn">{status}</span>;
}

function WalletTxnTable({ txns, emptyLabel }: { txns: PartnerDetail['wallet_transactions']; emptyLabel?: string }) {
  return (
    <table className="partners-table compact pp-table">
      <thead>
        <tr><th>TXN Reference</th><th>Type &amp; Description</th><th>Timestamp</th><th>Amount</th><th>Balance Post</th><th>Status</th></tr>
      </thead>
      <tbody>
        {txns.length === 0 ? (
          <tr><td colSpan={6} className="muted">{emptyLabel ?? 'No transactions.'}</td></tr>
        ) : txns.map((row) => (
          <tr key={row.id}>
            <td className="wd-ref">{row.reference_number}</td>
            <td><div>{row.title}</div><div className="muted">{row.txn_type.replace(/_/g, ' ')}</div></td>
            <td className="muted">{fmt(row.created_at)}</td>
            <td className={row.amount_cents >= 0 ? 'pp-txn-pos' : 'pp-txn-neg'}>{row.amount_cents >= 0 ? '+' : '−'}{money(Math.abs(row.amount_cents))}</td>
            <td>{row.balance_after_cents != null ? money(row.balance_after_cents) : '—'}</td>
            <td>{txnStatusPill(row.status)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type DeliveryRow = PartnerDeliveryRow | AdminDeliveryRow;

function isFullDeliveryRow(d: DeliveryRow): d is PartnerDeliveryRow {
  return 'mess_name' in d;
}

function deliveryStatusPill(status: string) {
  if (status === 'delivered') return <span className="pp-status-delivered">Delivered (On-Time)</span>;
  return <span className="pp-status-warn">{status.replace(/_/g, ' ')}</span>;
}

function DeliveryTable({ rows, showAll, compact, showViewAll }: { rows: DeliveryRow[]; showAll?: boolean; compact?: boolean; showViewAll?: number }) {
  const data = showAll ? rows : rows.slice(0, 5);
  const cols = compact ? 5 : 6;
  return (
    <>
      <table className="partners-table compact pp-table">
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Merchant / Kitchen</th>
            {!compact && <th>Drop Landmark</th>}
            <th>Time &amp; Dist</th>
            <th>Partner Earning</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr><td colSpan={cols} className="muted">No deliveries yet.</td></tr>
          ) : data.map((d) => (
            <tr key={d.delivery_id}>
              <td><span className="order-link">#DM-{d.order_id}</span>{d.is_test ? ' (TEST)' : ''}</td>
              <td>{isFullDeliveryRow(d) ? (d.mess_name ?? '—') : '—'}</td>
              {!compact && <td className="muted">{isFullDeliveryRow(d) ? d.dropoff_text : '—'}</td>}
              <td className="muted">
                {fmt(d.delivered_at ?? d.created_at)}
                {isFullDeliveryRow(d) && d.distance_km != null ? <div>{d.distance_km.toFixed(1)} km</div> : null}
              </td>
              <td><strong>{money(d.earning_cents)}</strong></td>
              <td>{deliveryStatusPill(d.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {showViewAll != null && rows.length > 5 && (
        <div style={{ textAlign: 'right', marginTop: 10 }}>
          <button type="button" className="link-btn">View All {showViewAll} Orders</button>
        </div>
      )}
    </>
  );
}

function OrderProgress({ step }: { step: number }) {
  return (
    <div className="pp-progress">
      {ORDER_STEPS.map((label, i) => (
        <div key={label} className={`pp-progress-step ${i < step ? 'done' : ''} ${i === step ? 'current' : ''}`}>
          {label}
        </div>
      ))}
    </div>
  );
}

function ActiveOrderCard({ order, full }: { order: NonNullable<PartnerDetail['active_order']>; full?: boolean }) {
  const statusLabel = order.status === 'picked_up' ? 'PICKED UP' : order.status.replace(/_/g, ' ').toUpperCase();
  return (
    <div className="pp-section-card pp-order-card">
      <div className="pp-section-head">
        <h3>{full ? 'Live Active Order' : 'Live Active Order'}</h3>
        <span className="pp-order-badge">{statusLabel}</span>
      </div>
      <div className="partner-name">Order #DM-{order.order_id}</div>
      <div className="pp-field-grid" style={{ marginTop: 14 }}>
        <div className="pp-field"><span className="pp-field-label">Pickup Restaurant</span><span className="pp-field-value">{order.pickup_label}</span></div>
        <div className="pp-field"><span className="pp-field-label">Drop Customer</span><span className="pp-field-value">{order.dropoff_text}</span></div>
        <div className="pp-field"><span className="pp-field-label">Order Value / Fare</span><span className="pp-field-value purple">{formatGmv(order.total_cents)}</span></div>
        <div className="pp-field"><span className="pp-field-label">ETA</span><span className="pp-field-value">{order.eta_minutes != null ? `${Math.round(order.eta_minutes)} mins` : '—'}</span></div>
      </div>
      <OrderProgress step={order.progress_step} />
    </div>
  );
}

function EditBankForm({ partner, inline, onClose, onSave }: { partner: PartnerDetail; inline?: boolean; onClose: () => void; onSave: (body: PartnerUpdatePayload) => Promise<void> }) {
  const [bankName, setBankName] = useState(partner.bank_name);
  const [accountMasked, setAccountMasked] = useState(partner.bank_account_masked);
  const [upiLinked, setUpiLinked] = useState(partner.upi_linked);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await onSave({ bank_name: bankName, bank_account_masked: accountMasked, upi_linked: upiLinked });
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Update failed');
      setBusy(false);
    }
  };

  const fields = (
    <>
      {err && <div className="card profile-alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="field"><label>Bank name</label><input value={bankName} onChange={(e) => setBankName(e.target.value)} /></div>
      <div className="field"><label>Account (masked)</label><input value={accountMasked} onChange={(e) => setAccountMasked(e.target.value)} placeholder="Last 4 digits" /></div>
      <div className="field"><label>IFSC (display only)</label><input value={partner.ifsc_code} disabled /></div>
      <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" id="upi-linked" checked={upiLinked} onChange={(e) => setUpiLinked(e.target.checked)} />
        <label htmlFor="upi-linked" style={{ margin: 0 }}>UPI linked</label>
      </div>
      {partner.upi_id && <div className="muted" style={{ marginBottom: 12 }}>UPI ID: {partner.upi_id}</div>}
      <div className="row">
        <button type="button" className="btn secondary sm" onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className="btn primary sm" onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save Bank Details'}</button>
      </div>
    </>
  );

  if (inline) return <div className="pp-bank-form">{fields}</div>;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Edit Bank &amp; UPI</h3>
        {fields}
      </div>
    </div>
  );
}

function EditBankModal(props: { partner: PartnerDetail; onClose: () => void; onSave: (body: PartnerUpdatePayload) => Promise<void> }) {
  return <EditBankForm {...props} />;
}

export function PartnerProfile() {
  const { riderId } = useParams();
  const navigate = useNavigate();
  const id = Number(riderId);
  const [p, setP] = useState<PartnerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [walletFilter, setWalletFilter] = useState<WalletFilter>('all');
  const [overviewTxnFilter, setOverviewTxnFilter] = useState<WalletFilter>('all');
  const [actionModal, setActionModal] = useState<ActionModal>(null);
  const [editBankOpen, setEditBankOpen] = useState(false);
  const [bankInlineEdit, setBankInlineEdit] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [noteBusy, setNoteBusy] = useState(false);

  const load = () => {
    setLoading(true);
    api.partner(id).then(setP).catch((e) => setError(e.message)).finally(() => setLoading(false));
  };

  useEffect(() => { if (Number.isFinite(id)) load(); }, [id]);

  const act = async (fn: () => Promise<PartnerDetail>) => {
    setError(null);
    try { setP(await fn()); } catch (e) { setError(e instanceof Error ? e.message : 'Failed'); throw e; }
  };

  const savePartner = async (body: PartnerUpdatePayload) => {
    await act(() => api.updatePartner(id, body));
  };

  const saveNote = async () => {
    const text = noteText.trim();
    if (!text) return;
    setNoteBusy(true);
    try {
      await act(() => api.addPartnerNote(id, text));
      setNoteText('');
    } finally {
      setNoteBusy(false);
    }
  };

  const filteredWalletTxns = useMemo(() => filterWalletTxns(p?.wallet_transactions ?? [], walletFilter), [p, walletFilter]);
  const overviewTxns = useMemo(() => filterWalletTxns((p?.wallet_transactions ?? []).slice(0, 8), overviewTxnFilter), [p, overviewTxnFilter]);

  return (
    <div className="content pp-page">
      <AsyncView data={p} loading={loading} error={error} onRetry={load} isEmpty={(d) => !d}>
        {(partner) => {
          const pendingWithdrawal = partner.wallet_transactions.find((x) => x.txn_type === 'withdrawal' && x.status === 'processing');
          return (
          <>
            <div className="pp-breadcrumb">
              <Link to="/">Console</Link> <span>›</span> Operations / <Link to="/partners">Delivery Partners</Link> / <strong>{partnerId(partner)}</strong>
            </div>

            <div className="pp-title-row">
              <div>
                <h1 className="pp-page-title">{partner.full_name}</h1>
                <div className="pp-status-row">
                  <span className="pp-badge pp-badge-green">Status: Active {partner.is_online ? '(Online)' : '(Offline)'}</span>
                  {partner.active_order && <span className="pp-badge pp-badge-green">Active — In Delivery</span>}
                  {partner.fleet_tier && <span className="pp-badge pp-badge-gold">{partner.fleet_tier}</span>}
                  {!partner.account_active && <span className="pp-badge pp-badge-red">Suspended</span>}
                </div>
              </div>
              <div className="pp-title-actions">
                <button type="button" className="btn secondary sm" onClick={() => navigate(`/partners/${id}/edit`)}>Edit Partner</button>
                <button type="button" className="btn primary sm" onClick={() => setTab('wallet')}>Adjust Wallet</button>
                {partner.account_active ? (
                  <button type="button" className="btn outline-danger sm" onClick={() => setActionModal('suspend')}>Suspend</button>
                ) : (
                  <button type="button" className="btn mint sm" onClick={() => setActionModal('reactivate')}>Reactivate</button>
                )}
              </div>
            </div>

            {partner.suspended_reason && <div className="card profile-alert">Suspended: {partner.suspended_reason}</div>}

            <div className="pp-summary-card">
              <div className="pp-summary-left">
                <div className="lt-avatar xl">{initials(partner.full_name)}</div>
                <div className="pp-summary-contact">
                  <div className="pp-summary-name">{partner.full_name}</div>
                  <div className="pp-summary-id">{partnerId(partner)}</div>
                  <div className="pp-verified">
                    {partner.phone_verified && <span>✓ Phone verified</span>}
                    {(partner.email || partner.contact_email) && <span>· ✓ Email verified</span>}
                  </div>
                  <div className="pp-summary-meta">{partner.operating_hub || 'Unassigned hub'} · {partner.tenure_months} months tenure</div>
                </div>
              </div>
              <div className="pp-summary-metrics">
                <div className="pp-metric"><div className="pp-metric-label">Lifetime Trips</div><div className="pp-metric-value">{partner.total_deliveries}</div></div>
                <div className="pp-metric"><div className="pp-metric-label">Cancel Rate</div><div className="pp-metric-value">{partner.cancel_rate_pct}%</div></div>
                <div className="pp-metric"><div className="pp-metric-label">Total Earned</div><div className="pp-metric-value purple">{formatGmv(partner.total_earned_cents)}</div></div>
                <div className="pp-metric"><div className="pp-metric-label">Current Order</div><div className="pp-metric-value sm">{partner.active_order_id ? `#DM-${partner.active_order_id}` : '—'}</div></div>
              </div>
            </div>

            <div className="pp-tabs-bar" role="tablist" aria-label="Partner sections">
              {tabList(partner).map((tb) => (
                <button key={tb.id} type="button" role="tab" aria-selected={tab === tb.id} className={`pp-tab ${tab === tb.id ? 'active' : ''}`} onClick={() => setTab(tb.id)} disabled={tb.id === 'active' && !partner.active_order}>
                  {tb.label}
                </button>
              ))}
            </div>

            <div className="pp-layout">
              <div className="pp-main">
                {tab === 'overview' && (
                  <>
                    {partner.active_order && <ActiveOrderCard order={partner.active_order} />}
                    <div className="pp-section-card">
                      <div className="pp-section-head">
                        <h3>Personal &amp; Fleet Information</h3>
                        <button type="button" className="btn secondary sm" onClick={() => navigate(`/partners/${id}/edit`)}>Quick Edit</button>
                      </div>
                      <div className="pp-field-grid">
                        <div className="pp-field"><span className="pp-field-label">Full Legal Name</span><span className="pp-field-value">{partner.full_name}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Primary Mobile</span><span className="pp-field-value">{partner.phone ?? '—'}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Emergency Contact</span><span className="pp-field-value">{partner.emergency_contact || '—'}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Email</span><span className="pp-field-value">{partner.email ?? partner.contact_email ?? '—'}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Assigned Delivery Cluster</span><span className="pp-field-value">{partner.operating_hub || 'Unassigned'}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Fleet Tier</span><span className="pp-field-value">{partner.fleet_tier || '—'}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Vehicle</span><span className="pp-field-value">{partner.vehicle_model || partner.vehicle_type} · {partner.vehicle_number}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Shift Preference</span><span className="pp-field-value">{partner.shift_preference}</span></div>
                        <div className="pp-field"><span className="pp-field-label">Max Active Orders Cap</span><span className="pp-field-value">{partner.max_active_orders}</span></div>
                        <div className="pp-field"><span className="pp-field-label">License / RC</span><span className="pp-field-value">{partner.license_number} · {partner.rc_status}</span></div>
                      </div>
                    </div>
                    <div className="pp-section-card">
                      <div className="pp-section-head">
                        <h3>Registered Bank &amp; Payout Node</h3>
                        <button type="button" className="btn secondary sm" onClick={() => setTab('bank')}>Edit Bank / UPI</button>
                      </div>
                      <div className="pp-bank-split">
                        <div className="pp-bank-panel">
                          <div className="pp-section-head" style={{ marginBottom: 8 }}>
                            <h4>Bank Details</h4>
                            <span className="pp-kyc-ok">Penny-Drop Verified</span>
                          </div>
                          <div className="pp-field-value">{partner.bank_name || '—'}</div>
                          <div className="muted">Account •••• {partner.bank_account_masked}</div>
                          <div className="muted">IFSC {partner.ifsc_code}</div>
                          <div className="muted" style={{ marginTop: 8 }}>{partner.full_name} — 100% KYC Match</div>
                        </div>
                        <div className="pp-bank-panel">
                          <div className="pp-section-head" style={{ marginBottom: 8 }}>
                            <h4>UPI Details</h4>
                            {partner.upi_linked && <span className="pp-kyc-ok">NPCI Active</span>}
                          </div>
                          <div className="pp-field-value">{partner.upi_id ?? '—'}</div>
                          <div className="muted">IMPS / UPI 2.0 Auto</div>
                          <div className="muted" style={{ marginTop: 8 }}>Daily Limit: {money(partner.daily_cashout_limit_cents)}</div>
                        </div>
                      </div>
                    </div>
                    <div className="pp-section-card">
                      <div className="pp-section-head"><h3>Recent Delivery Assignments</h3><button type="button" className="link-btn" onClick={() => setTab('history')}>View All {partner.total_deliveries} Orders</button></div>
                      <DeliveryTable rows={partner.delivery_history.length ? partner.delivery_history : partner.recent_deliveries} showViewAll={partner.total_deliveries} />
                    </div>
                    <div className="pp-section-card">
                      <div className="wd-card-head">
                        <h3>Recent Wallet Transactions &amp; Payouts</h3>
                      </div>
                      <div className="pp-filter-chips">
                        {(['all', 'credits', 'withdrawals', 'bonuses'] as WalletFilter[]).map((f) => (
                          <button key={f} type="button" className={`chip ${overviewTxnFilter === f ? 'active' : ''}`} onClick={() => setOverviewTxnFilter(f)}>{f.charAt(0).toUpperCase() + f.slice(1)}</button>
                        ))}
                      </div>
                      <WalletTxnTable txns={overviewTxns} emptyLabel="No matching transactions." />
                    </div>
                  </>
                )}

                {tab === 'active' && (
                  partner.active_order ? (
                    <ActiveOrderCard order={partner.active_order} full />
                  ) : (
                    <div className="pp-section-card"><p className="muted">No active delivery right now.</p></div>
                  )
                )}

                {tab === 'history' && (
                  <div className="pp-section-card">
                    <h3>Delivery History</h3>
                    <DeliveryTable rows={partner.delivery_history} showAll />
                  </div>
                )}

                {tab === 'bank' && (
                  <div className="pp-section-card">
                    <div className="wd-card-head">
                      <h3>Registered Bank &amp; Payout Node</h3>
                      {!bankInlineEdit && (
                        <button type="button" className="btn secondary sm" onClick={() => setBankInlineEdit(true)}>Edit Bank / UPI</button>
                      )}
                    </div>
                    {bankInlineEdit ? (
                      <EditBankForm partner={partner} inline onClose={() => setBankInlineEdit(false)} onSave={savePartner} />
                    ) : (
                      <>
                        <div className="pp-bank-split">
                          <div className="pp-bank-panel">
                            <div className="pp-section-head" style={{ marginBottom: 8 }}>
                              <h4>Bank Details</h4>
                              <span className="pp-kyc-ok">Penny-Drop Verified</span>
                            </div>
                            <div className="pp-field-value">{partner.bank_name || '—'}</div>
                            <div className="muted">Account •••• {partner.bank_account_masked}</div>
                            <div className="muted">IFSC {partner.ifsc_code}</div>
                            <div className="muted" style={{ marginTop: 8 }}>{partner.full_name} — 100% KYC Match</div>
                          </div>
                          <div className="pp-bank-panel">
                            <div className="pp-section-head" style={{ marginBottom: 8 }}>
                              <h4>UPI Details</h4>
                              {partner.upi_linked && <span className="pp-kyc-ok">NPCI Active</span>}
                            </div>
                            <div className="pp-field-value">{partner.upi_id ?? '—'}</div>
                            <div className="muted">IMPS / UPI 2.0 Auto</div>
                            <div className="muted" style={{ marginTop: 8 }}>Daily Limit: {money(partner.daily_cashout_limit_cents)}</div>
                          </div>
                        </div>
                        <div className="pp-security-note">Bank or UPI changes require dual verification (SMS OTP + Supervisor Approval) before going live.</div>
                      </>
                    )}
                  </div>
                )}

                {tab === 'wallet' && (
                  <div className="pp-section-card">
                    <div className="wd-card-head">
                      <h3>Wallet Transactions</h3>
                      <span className="muted">{filteredWalletTxns.length} entries</span>
                    </div>
                    <div className="pp-filter-chips">
                      {(['all', 'credits', 'withdrawals', 'bonuses'] as WalletFilter[]).map((f) => (
                        <button key={f} type="button" className={`chip ${walletFilter === f ? 'active' : ''}`} onClick={() => setWalletFilter(f)}>{f.charAt(0).toUpperCase() + f.slice(1)}</button>
                      ))}
                    </div>
                    <WalletTxnTable txns={filteredWalletTxns} />
                  </div>
                )}
              </div>

              <aside className="pp-sidebar">
                <div className="pp-wallet-card">
                  <h3>Partner Wallet Balance</h3>
                  <div className="pp-wallet-total">{money(partner.wallet_total_cents)}</div>
                  <div className="pp-wallet-split">
                    <div><span>Available to Withdraw</span><strong>{money(partner.wallet_available_cents)}</strong></div>
                    <div><span>Escrow / COD Held</span><strong>{money(partner.wallet_locked_cents)}</strong></div>
                  </div>
                  {(partner.payout_pending || pendingWithdrawal) && (
                    <div className="pp-pending-alert">
                      Pending Cashout Request: {pendingWithdrawal ? money(Math.abs(pendingWithdrawal.amount_cents)) : 'In queue'} — awaiting approval
                    </div>
                  )}
                  <button type="button" className="btn secondary sm" style={{ width: '100%', marginTop: 12, background: 'rgba(255,255,255,0.15)', color: '#fff', border: '1px solid rgba(255,255,255,0.3)' }}>Issue Manual Adjustment / Bonus</button>
                </div>

                <div className="pp-section-card">
                  <div className="pp-section-head"><h3>Compliance &amp; KYC</h3><span className="pp-kyc-ok">Verified</span></div>
                  <div className="pp-kyc-list">
                    {partner.kyc_items.map((k) => (
                      <div key={k.label} className="pp-kyc-row">
                        <span>{k.label}</span>
                        <span className={k.ok ? 'pp-kyc-ok' : 'pp-status-warn'}>{k.ok ? 'Verified' : k.status}</span>
                      </div>
                    ))}
                    <div className="pp-kyc-row"><span>Background Verification</span><span className="pp-kyc-ok">Active</span></div>
                  </div>
                  <button type="button" className="btn secondary sm" style={{ width: '100%', marginTop: 12 }}>Upload Renewed Documents</button>
                </div>

                <div className="pp-section-card">
                  <h3>Issued Assets &amp; Kit</h3>
                  <div className="pp-assets-list">
                    <div className="pp-asset-row"><span>Delivery Bag (Thermal)</span><span className="pp-kyc-ok">Issued</span></div>
                    <div className="pp-asset-row"><span>Raincoat</span><span className="pp-kyc-ok">Issued</span></div>
                    <div className="pp-asset-row"><span>Khana Delivery T-Shirt (×2)</span><span className="pp-kyc-ok">Issued</span></div>
                  </div>
                </div>

                <div className="pp-section-card">
                  <h3>Internal Admin Notes</h3>
                  <div className="pp-note-feed">
                    {partner.admin_notes.length === 0 ? (
                      <div className="muted">No admin notes yet.</div>
                    ) : partner.admin_notes.map((n) => (
                      <div key={n.id} className="pp-note-item">
                        <div>{n.text}</div>
                        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{fmt(n.created_at)}</div>
                      </div>
                    ))}
                  </div>
                  <textarea className="wd-note" rows={3} value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder="Add an internal note…" />
                  <button type="button" className="btn primary sm" style={{ width: '100%' }} disabled={noteBusy || !noteText.trim()} onClick={saveNote}>
                    {noteBusy ? 'Saving…' : 'Save Note to Partner File'}
                  </button>
                </div>

                {partner.open_issues.length > 0 && (
                  <div className="card wd-detail-card">
                    <h3>Open Issues</h3>
                    {partner.open_issues.map((i) => (
                      <div key={i.id} className="profile-issue">#{i.order_id} · {i.issue_type}: {i.note}</div>
                    ))}
                  </div>
                )}
              </aside>
            </div>

            {partner.active_order_id && tab === 'overview' && (
              <button type="button" className="btn secondary sm" onClick={() => navigate('/operations')}>View on Live Tracking</button>
            )}
          </>
          );
        }}
      </AsyncView>

      {editBankOpen && p && (
        <EditBankModal partner={p} onClose={() => setEditBankOpen(false)} onSave={savePartner} />
      )}
      {actionModal === 'suspend' && (
        <ReasonModal title="Suspend partner" confirmLabel="Suspend" onConfirm={(r) => act(() => api.suspend(id, r))} onClose={() => setActionModal(null)} />
      )}
      {actionModal === 'reactivate' && (
        <ReasonModal title="Reactivate partner" confirmLabel="Reactivate" onConfirm={(r) => act(() => api.reactivate(id, r))} onClose={() => setActionModal(null)} />
      )}
    </div>
  );
}
