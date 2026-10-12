import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { AsyncView } from '@/ui/kit';
import { money } from '@/theme';

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}

function fmt(iso: string) {
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function activeSince(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}

export function WithdrawalDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const txnId = Number(id);
  const [acting, setActing] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [adminNote, setAdminNote] = useState('');

  const { data, loading, error, reload } = useAsync(
    () => api.withdrawal(txnId),
    [txnId],
    10000,
  );

  const approve = async () => {
    setActing(true);
    try { await api.approveWithdrawal(txnId); navigate('/withdrawals'); } finally { setActing(false); }
  };

  const reject = async (reason: string) => {
    setActing(true);
    try { await api.rejectWithdrawal(txnId, reason); navigate('/withdrawals'); } finally { setActing(false); }
  };

  return (
    <div className="content wd-detail-page">
      <AsyncView data={data} loading={loading} error={error} onRetry={reload}>
        {(d) => (
          <>
            <div className="wd-detail-breadcrumb muted">
              Withdrawal Requests / #{d.reference_number} — {d.rider_name}
            </div>
            <div className="wd-detail-head">
              <div>
                <h1 className="dispatch-title">Withdrawal Inspection &amp; Sign-off</h1>
                {d.status === 'pending_review' && <span className="wd-signoff-badge">PENDING ADMIN SIGN-OFF</span>}
                {d.status === 'approved' && <span className="wd-signoff-badge approved">DISBURSED</span>}
                {d.status === 'rejected' && <span className="wd-signoff-badge rejected">REJECTED</span>}
              </div>
              <div className="dispatch-actions">
                <Link to="/withdrawals" className="btn secondary sm">Back to list</Link>
              </div>
            </div>

            <div className="wd-detail-layout">
              <div className="wd-detail-main">
                <div className="card wd-detail-card">
                  <div className="wd-req-top">
                    <div>
                      <div className="wd-ref">Request #{d.reference_number}</div>
                      <div className="muted">Submitted {fmt(d.created_at)}</div>
                    </div>
                    <div className="wd-payout-amount">
                      <div className="wd-amount-xl">{money(d.net_amount_cents)}</div>
                      <div className="muted">{d.fee_cents === 0 ? 'ZERO FEE' : `Fee ${money(d.fee_cents)}`}</div>
                    </div>
                  </div>
                  <div className="wd-tags">
                    <span className="wd-cycle">Payout Request</span>
                    {d.priority_queue && <span className="wd-cycle">Priority Fast-Track Queue</span>}
                    <span className="muted">{d.payout_cycle}</span>
                  </div>
                </div>

                <div className="card wd-detail-card">
                  <div className="wd-card-head">
                    <h3>Partner Identification &amp; KYC Status</h3>
                    <span className="ver-pill ver-ok">{d.partner.kyc_compliance_pct}% Fully Compliant</span>
                  </div>
                  <div className="wd-partner-row">
                    <div className="lt-avatar xl">{initials(d.partner.full_name)}</div>
                    <div>
                      <div className="partner-name">{d.partner.full_name}</div>
                      <div className="partner-meta">{d.partner.partner_code} · {d.partner.operating_hub}</div>
                      <div className="partner-meta">★ {d.partner.rating != null ? d.partner.rating.toFixed(2) : '—'} ({d.partner.total_deliveries}+ trips) · Active since {activeSince(d.partner.active_since)}</div>
                      {d.partner.fleet_tier && <span className="wd-tier">{d.partner.fleet_tier}</span>}
                    </div>
                  </div>
                  <div className="wd-kyc-grid">
                    {d.partner.kyc_items.map((k) => (
                      <div key={k.label} className={`wd-kyc-item ${k.ok ? 'ok' : 'warn'}`}>
                        <div className="wd-kyc-label">{k.label}</div>
                        <div>{k.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card wd-detail-card">
                  <div className="wd-card-head">
                    <h3>Wallet &amp; Liquidity Breakdown</h3>
                    <span className="muted">Daily limit remaining: {money(d.wallet.daily_limit_remaining_cents)}</span>
                  </div>
                  <div className="wd-wallet-grid">
                    <div><span className="muted">Gross Wallet Total</span><strong>{money(d.wallet.gross_total_cents)}</strong></div>
                    <div><span className="muted">Escrow / Locked</span><strong>{money(d.wallet.escrow_locked_cents)}</strong></div>
                    <div><span className="muted">Available Cashout</span><strong>{money(d.wallet.available_cashout_cents)}</strong></div>
                    <div><span className="muted">Post-Withdrawal Rem.</span><strong>{money(d.wallet.post_withdrawal_cents)}</strong></div>
                  </div>
                  <div className="fleet-bar" style={{ marginTop: 12 }}><div className="fleet-fill" style={{ width: `${Math.min(100, d.wallet.daily_utilization_pct)}%` }} /></div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{d.wallet.daily_utilization_pct}% of daily regulatory limit used</div>
                </div>

                <div className="card wd-detail-card">
                  <div className="wd-card-head">
                    <h3>Destination Bank Node (Beneficiary)</h3>
                    {d.bank.penny_drop_verified && <span className="ver-pill ver-ok">Penny Drop Verified</span>}
                  </div>
                  <div className="partner-name">{d.bank.bank_name}</div>
                  <div className="muted">Account •••• {d.bank.account_masked} · IFSC {d.bank.ifsc_code}</div>
                  <div className="muted">{d.bank.account_holder}</div>
                </div>

                <div className="card wd-detail-card">
                  <h3>Earning Components in this Request</h3>
                  <table className="partners-table compact">
                    <thead><tr><th>Item / Reference</th><th>Category</th><th>Timestamp</th><th>Status</th><th>Credited</th></tr></thead>
                    <tbody>
                      {d.earning_components.length === 0 ? (
                        <tr><td colSpan={5} className="muted">No ledger lines found.</td></tr>
                      ) : d.earning_components.map((e) => (
                        <tr key={e.reference + e.timestamp}>
                          <td>{e.title}<div className="muted">{e.reference}</div></td>
                          <td>{e.category}</td>
                          <td className="muted">{fmt(e.timestamp)}</td>
                          <td>{e.status}</td>
                          <td><strong>{money(e.amount_cents)}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="wd-ledger-total">Total Ledger Sum (Ready for Instant Disbursal): <strong>{money(d.net_amount_cents)}</strong></div>
                </div>

                <div className="card wd-detail-card">
                  <h3>Previous Payout History</h3>
                  <table className="partners-table compact">
                    <thead><tr><th>Payout ID</th><th>Date &amp; Time</th><th>Amount</th><th>Mode</th><th>UTR / Ref</th><th>Status</th></tr></thead>
                    <tbody>
                      {d.payout_history.length === 0 ? (
                        <tr><td colSpan={6} className="muted">No prior payouts.</td></tr>
                      ) : d.payout_history.map((p) => (
                        <tr key={p.reference_number}>
                          <td>{p.reference_number}</td>
                          <td className="muted">{fmt(p.created_at)}</td>
                          <td>{money(p.amount_cents)}</td>
                          <td>{p.mode}</td>
                          <td className="muted">{p.utr || '—'}</td>
                          <td><span className="ver-pill ver-ok">{p.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <aside className="wd-detail-side">
                <div className="card wd-detail-card wd-risk-card">
                  <h3>Risk &amp; Trust Score</h3>
                  <div className="wd-risk-gauge">
                    <div className="wd-risk-score">{d.risk.score}</div>
                    <div className="muted">{d.risk.label}</div>
                  </div>
                  <ul className="wd-trust-list">
                    {d.risk.checks.map((c) => (
                      <li key={c.label} className={c.ok ? 'ok' : 'bad'}>{c.ok ? '✓' : '✕'} {c.label}</li>
                    ))}
                  </ul>
                </div>

                <div className="card wd-detail-card">
                  <h3>Disbursal Action Suite</h3>
                  <label className="muted">Admin Log Note</label>
                  <textarea className="wd-note" rows={3} value={adminNote} onChange={(e) => setAdminNote(e.target.value)} placeholder="Automated checks passed. Bank penny-drop verified." />
                  {d.status === 'pending_review' && (
                    <>
                      <label className="muted">Rejection reason</label>
                      <select className="partners-vehicle" style={{ width: '100%', marginBottom: 12 }} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}>
                        <option value="">-- Select reason only if rejecting request --</option>
                        {d.reject_reasons.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                      <button type="button" className="btn primary" style={{ width: '100%', marginBottom: 8 }} disabled={acting} onClick={approve}>
                        Approve &amp; Disburse {money(d.net_amount_cents)}
                      </button>
                      <button type="button" className="btn danger sm" style={{ width: '100%' }} disabled={acting || !rejectReason} onClick={() => reject(rejectReason)}>Reject Withdrawal</button>
                    </>
                  )}
                  {d.admin_note && <div className="profile-alert" style={{ marginTop: 12 }}>{d.admin_note}</div>}
                </div>

              </aside>
            </div>
          </>
        )}
      </AsyncView>

    </div>
  );
}
