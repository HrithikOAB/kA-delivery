import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { AsyncView, ReasonModal } from '@/ui/kit';
import { formatGmv, money } from '@/theme';
import type { WithdrawalRequest } from '@/api/types';

type Tab = 'all' | 'pending_review' | 'approved' | 'rejected';

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function exportCsv(rows: WithdrawalRequest[]) {
  const header = ['Reference', 'Partner', 'Amount', 'Bank', 'Status', 'Risk'];
  const lines = rows.map((r) => [r.reference_number, r.rider_name, money(r.amount_cents), r.bank_name, r.status, `${r.risk_score}`].map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','));
  const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'withdrawal-audit.csv'; a.click();
  URL.revokeObjectURL(url);
}

export function Withdrawals() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('pending_review');
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [acting, setActing] = useState(false);

  const { data, loading, error, stale, reload } = useAsync(async () => {
    const [summary, page] = await Promise.all([
      api.withdrawalsSummary(),
      api.withdrawals({ status: tab === 'all' ? undefined : tab, q: q || undefined }),
    ]);
    return { summary, page };
  }, [tab, q], 15000);

  const rows = data?.page.items ?? [];
  const s = data?.summary;

  const counts = useMemo(() => ({
    all: s?.total_count ?? 0,
    pending: s?.pending_count ?? 0,
    approved: s?.approved_today_count ?? 0,
    rejected: s?.rejected_count ?? 0,
  }), [s]);

  const toggle = (id: number) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const approveOne = async (id: number) => {
    setActing(true);
    try { await api.approveWithdrawal(id); reload(); } finally { setActing(false); }
  };

  const bulkApprove = async () => {
    if (!selected.size) return;
    setActing(true);
    try { await api.bulkApproveWithdrawals(Array.from(selected)); setSelected(new Set()); reload(); } finally { setActing(false); }
  };

  const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <div className="content withdrawals-page">
      <div className="wd-breadcrumb muted">FINANCE GOVERNANCE / PAYOUT CONTROL SUITE</div>
      <div className="partners-head">
        <div>
          <h1 className="dispatch-title">Withdrawal Requests &amp; Approvals</h1>
          <p className="muted dispatch-sub">Real-time payout auditing and IMPS settlement governance</p>
          <div className="wd-gateway-chip">Settlement Gateway IMPS Direct Node: <strong>{s?.gateway_status === 'operational' ? 'Operational' : 'Degraded'}</strong></div>
        </div>
        <div className="dispatch-actions">
          <button type="button" className="btn secondary sm">Reconcile Ledgers</button>
          <button type="button" className="btn primary sm" onClick={() => exportCsv(rows)}>Export Audit CSV</button>
        </div>
      </div>

      <AsyncView data={data} loading={loading} error={error} onRetry={reload} stale={stale}>
        {() => (
          <>
            <div className="wd-kpi-grid">
              <div className="kpi-card kpi-yellow">
                <span className="kpi-label">Pending Approvals</span>
                <div className="kpi-value">{counts.pending}</div>
                <div className="kpi-sub">{formatGmv(s?.pending_amount_cents ?? 0)}</div>
                <span className="pending-badge">Action Required</span>
              </div>
              <div className="kpi-card kpi-green">
                <span className="kpi-label">Approved Today</span>
                <div className="kpi-value">{counts.approved}</div>
                <div className="kpi-sub">{formatGmv(s?.approved_today_amount_cents ?? 0)}</div>
                <span className="chip">Via IMPS Instant</span>
              </div>
              <div className="kpi-card kpi-neutral">
                <span className="kpi-label">Rejected / Flagged</span>
                <div className="kpi-value">{counts.rejected}</div>
                <div className="kpi-sub">{formatGmv(s?.rejected_amount_cents ?? 0)}</div>
                <span className="chip danger">Account Mismatch</span>
              </div>
              <div className="kpi-card kpi-escrow">
                <span className="kpi-label">Escrow Reserve Balance</span>
                <div className="kpi-value escrow">{formatGmv(s?.escrow_reserve_cents ?? 0)}</div>
                <div className="kpi-sub">RBI Compliant Pool · {s?.liquidity_ratio ?? 0}x Liquidity</div>
              </div>
            </div>

            <div className="wd-toolbar">
              <div className="partners-segments">
                {([['all', `All Requests (${counts.all})`], ['pending_review', `Pending Review (${counts.pending})`], ['approved', `Approved (${counts.approved})`], ['rejected', `Rejected (${counts.rejected})`]] as [Tab, string][]).map(([id, label]) => (
                  <button key={id} type="button" className={`seg-btn ${tab === id ? 'active' : ''}`} onClick={() => { setTab(id); setSelected(new Set()); }}>{label}</button>
                ))}
              </div>
              <span className="date-pill">Today: {today}</span>
              <button type="button" className="btn secondary sm" disabled={!selected.size || acting} onClick={bulkApprove}>Approve Selected ({selected.size})</button>
              <button type="button" className="btn ghost sm">Export Bank IMPS File</button>
            </div>

            <div className="wd-search-row">
              <input className="partners-search" placeholder="Partner Name, ID, or Account Number…" aria-label="Search withdrawals" value={q} onChange={(e) => setQ(e.target.value)} />
              <div className="wd-legend muted">
                <span>Auto-Disbursement: On (&lt;₹5,000)</span>
                <span>Manual Sign-off (&gt;₹5,000)</span>
              </div>
            </div>

            <div className="card partners-table-wrap">
              <table className="partners-table wd-table">
                <thead>
                  <tr>
                    <th>Request ID &amp; Time</th>
                    <th>Delivery Partner</th>
                    <th>Amount Requested</th>
                    <th>Wallet Snapshot</th>
                    <th>Destination Bank</th>
                    <th>Risk Matrix</th>
                    <th>Status &amp; Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 32 }}>No withdrawal requests in this queue.</td></tr>
                  ) : rows.map((r) => (
                    <tr key={r.id} className="clickable" onClick={() => navigate(`/withdrawals/${r.id}`)} style={{ cursor: 'pointer' }}>
                      <td>
                        <div className="wd-ref">#{r.reference_number}</div>
                        <div className="muted">{formatTime(r.created_at)}</div>
                        <span className="wd-cycle">{r.payout_cycle}</span>
                      </td>
                      <td>
                        <div className="partner-cell">
                          <div className="lt-avatar sm">{initials(r.rider_name)}</div>
                          <div>
                            <div className="partner-name">{r.rider_name}</div>
                            <div className="partner-meta">{r.partner_code} · ★ {r.rating != null ? r.rating.toFixed(1) : '—'}</div>
                            {r.fleet_tier && <span className="wd-tier">{r.fleet_tier}</span>}
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="wd-amount">{money(r.amount_cents)}</div>
                        <div className="muted">{r.requires_dual_signoff ? 'Dual-Admin Sign-off' : 'Zero Commission Fee'}</div>
                      </td>
                      <td>
                        <div><strong>{money(r.wallet_balance_cents)}</strong> <span className="muted">current</span></div>
                        <div className="muted">→ {money(r.post_cashout_balance_cents)} post-cashout</div>
                      </td>
                      <td>
                        <div className="partner-name">{r.bank_name} {r.bank_verified && <span className="ver-ok">✓</span>}</div>
                        <div className="muted">•••• {r.bank_account_masked}</div>
                        <div className="muted">{r.ifsc_code} · {r.account_holder}</div>
                      </td>
                      <td>
                        <span className={`risk-pill ${r.risk_score >= 95 ? 'low' : r.risk_score >= 85 ? 'med' : 'high'}`}>{r.risk_label} · {r.risk_score}/100</span>
                        <div className="muted wd-risk-note">{r.risk_note}</div>
                      </td>
                      <td>
                        <span className={`wd-status ${r.status}`}>{r.status === 'pending_review' ? 'PENDING REVIEW' : r.status.toUpperCase()}</span>
                        <button type="button" className="btn primary xs" onClick={(e) => { e.stopPropagation(); navigate(`/withdrawals/${r.id}`); }}>Inspect</button>
                        {r.status === 'pending_review' && (
                          <div className="partner-actions" style={{ marginTop: 8 }}>
                            <label className="wd-check" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} /></label>
                            <button type="button" className="btn mint xs" disabled={acting} onClick={(e) => { e.stopPropagation(); approveOne(r.id); }}>Approve</button>
                            <button type="button" className="btn danger xs" disabled={acting} onClick={(e) => { e.stopPropagation(); setRejectId(r.id); }}>Reject</button>
                          </div>
                        )}
                        {r.admin_note && <div className="muted wd-risk-note">{r.admin_note}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="wd-footer-panels">
              <div className="card wd-panel">
                <h4>IMPS Node Health</h4>
                <div className="wd-panel-stat success">{s?.imps_success_rate ?? 99.98}% success</div>
                <div className="muted">Latency {s?.imps_latency_seconds ?? 1.8}s · Daily cap {s?.daily_cap_used_pct ?? 42}% used</div>
              </div>
              <div className="card wd-panel">
                <h4>TDS &amp; 194C Compliance</h4>
                <div className="wd-panel-stat">{formatGmv(s?.tds_ytd_cents ?? 0)} YTD</div>
                <div className="muted">Today TDS {money(s?.tds_today_cents ?? 0)} · <button type="button" className="link-btn">Generate Form 16A</button></div>
              </div>
              <div className="card wd-panel">
                <h4>Fraud Detection Rules</h4>
                <div className="wd-panel-stat warn">{s?.fraud_rules_triggered ?? 0} Active Rules Triggered</div>
                <div className="muted">Rule 04: Mobile number mismatch · <button type="button" className="link-btn">Tune Heuristics</button></div>
              </div>
            </div>
          </>
        )}
      </AsyncView>

      {rejectId !== null && (
        <ReasonModal
          title="Reject withdrawal"
          confirmLabel="Reject"
          onConfirm={async (reason) => { setActing(true); try { await api.rejectWithdrawal(rejectId, reason); setRejectId(null); reload(); } finally { setActing(false); } }}
          onClose={() => setRejectId(null)}
        />
      )}
    </div>
  );
}
