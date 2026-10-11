import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { AsyncView } from '@/ui/kit';
import { money } from '@/theme';
import type { PartnerListItem } from '@/api/types';

type Segment = 'all' | 'online' | 'offline' | 'pending' | 'suspended';
const PAGE_SIZE = 10;

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}
function partnerId(p: PartnerListItem) {
  return p.partner_code ?? `DM-${String(p.rider_id).padStart(4, '0')}`;
}
function vehicleTag(type: string) {
  const t = type.toLowerCase();
  if (t.includes('bicycle') || t === 'cycle') return { label: 'Bicycle', cls: 'veh-green' };
  if (t.includes('ev') || t.includes('electric')) return { label: 'EV Scooter', cls: 'veh-teal' };
  return { label: 'Two-Wheeler', cls: 'veh-blue' };
}
function verificationMeta(status: string) {
  if (status === 'approved') return { label: 'Verified', cls: 'ver-ok' };
  if (['submitted', 'under_review', 'pending'].includes(status)) return { label: 'Pending Docs', cls: 'ver-warn' };
  return { label: 'Action Required', cls: 'ver-danger' };
}
function lastSeenLabel(iso: string | null): string | null {
  if (!iso) return null;
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'seen just now';
  if (mins < 60) return `seen ${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `seen ${hrs}h ago`;
  return `seen ${Math.floor(hrs / 24)}d ago`;
}
function fleetStatus(p: PartnerListItem) {
  if (!p.account_active) return { label: 'SUSPENDED', cls: 'fleet-suspended', sub: p.suspended_reason };
  if (p.is_online && p.active_order_id) return { label: 'ONLINE', cls: 'fleet-online', sub: `Order #${p.active_order_id}` };
  if (p.is_online && p.payout_pending) return { label: 'BUSY', cls: 'fleet-busy', sub: 'Payout processing' };
  if (p.is_online) return { label: 'ONLINE', cls: 'fleet-online', sub: lastSeenLabel(p.last_seen_at) };
  return { label: 'OFFLINE', cls: 'fleet-offline', sub: lastSeenLabel(p.last_seen_at) };
}
function exportCsv(rows: PartnerListItem[]) {
  const header = ['Name', 'Partner ID', 'Phone', 'Hub', 'Vehicle', 'Status', 'Trips', 'Wallet', 'Week Earnings'];
  const lines = rows.map((p) => {
    const st = fleetStatus(p);
    return [p.full_name, partnerId(p), p.phone ?? '', p.operating_hub, `${p.vehicle_model} ${p.vehicle_number}`, st.label, String(p.total_deliveries), money(p.wallet_balance_cents), money(p.week_earnings_cents)].map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',');
  });
  const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'digimess-fleet-roster.csv'; a.click();
  URL.revokeObjectURL(url);
}

export function Partners() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [segment, setSegment] = useState<Segment>('all');
  const [vehicle, setVehicle] = useState('');
  const [page, setPage] = useState(0);
  const { data, loading, error, stale, reload } = useAsync(async () => {
    const [partners, overview] = await Promise.all([api.partners({ q: q || undefined }), api.overview()]);
    return { partners, overview };
  }, [q], 20000);

  const filtered = useMemo(() => (data?.partners.items ?? []).filter((p) => {
    if (segment === 'online' && !p.is_online) return false;
    if (segment === 'offline' && p.is_online) return false;
    if (segment === 'pending' && !['submitted', 'under_review', 'pending'].includes(p.approval_status)) return false;
    if (segment === 'suspended' && p.account_active) return false;
    if (vehicle && p.vehicle_type.toLowerCase() !== vehicle.toLowerCase()) return false;
    return true;
  }), [data, segment, vehicle]);

  const counts = useMemo(() => {
    const items = data?.partners.items ?? [];
    return { all: items.length, online: items.filter((p) => p.is_online).length, offline: items.filter((p) => !p.is_online).length, pending: items.filter((p) => ['submitted', 'under_review', 'pending'].includes(p.approval_status)).length, suspended: items.filter((p) => !p.account_active).length };
  }, [data]);

  const avgRating = useMemo(() => {
    const rated = (data?.partners.items ?? []).filter((p) => p.rating != null);
    return rated.length ? (rated.reduce((s, p) => s + (p.rating ?? 0), 0) / rated.length).toFixed(2) : '—';
  }, [data]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const m = data?.overview.metrics;

  return (
    <div className="content partners-page">
      <div className="partners-head">
        <div>
          <h1 className="dispatch-title">Delivery Partners Management</h1>
          <p className="muted dispatch-sub">Fleet roster, verification status, and partner payouts</p>
        </div>
        <div className="dispatch-actions">
          <button type="button" className="btn secondary sm" onClick={() => exportCsv(filtered)}>Export Fleet Roster</button>
          <button type="button" className="btn primary sm" onClick={() => navigate('/verification')}>+ Register New Partner</button>
        </div>
      </div>
      <AsyncView data={data} loading={loading} error={error} onRetry={reload} stale={stale}>
        {() => (
          <>
            <div className="kpi-grid partners-kpis">
              <div className="kpi-card kpi-neutral"><span className="kpi-label">Total Registered</span><div className="kpi-value">{data?.partners.total ?? m?.approved_partners ?? 0}</div><div className="kpi-sub muted">+{m?.pending_applications ?? 0} pending review</div></div>
              <div className="kpi-card kpi-green"><span className="kpi-label">Active &amp; Online Today</span><div className="kpi-value">{m?.online_partners ?? counts.online}</div><div className="kpi-sub muted">{counts.online} online · {counts.offline} idle/offline</div></div>
              <div className="kpi-card kpi-yellow"><span className="kpi-label">Pending Verification</span><div className="kpi-value">{m?.pending_applications ?? counts.pending}</div><span className="pending-badge">Requires Review</span></div>
              <div className="kpi-card kpi-purple"><span className="kpi-label">Avg Fleet Rating</span><div className="kpi-value">{avgRating}<span className="kpi-denom"> / 5.0</span></div></div>
            </div>
            <div className="partners-toolbar">
              <input className="partners-search" placeholder="Search partners by name or phone…" aria-label="Search partners" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
              <div className="partners-segments" role="tablist" aria-label="Partner filters">
                {([['all', `All (${counts.all})`], ['online', `Online (${counts.online})`], ['offline', `Offline (${counts.offline})`], ['pending', `Pending (${counts.pending})`], ['suspended', `Suspended (${counts.suspended})`]] as [Segment, string][]).map(([id, label]) => (
                  <button key={id} type="button" role="tab" aria-selected={segment === id} className={`seg-btn ${segment === id ? 'active' : ''}`} onClick={() => { setSegment(id); setPage(0); }}>{label}</button>
                ))}
              </div>
              <select className="partners-vehicle" value={vehicle} onChange={(e) => { setVehicle(e.target.value); setPage(0); }} aria-label="Vehicle type">
                <option value="">All Vehicles</option><option value="bike">Two-Wheeler</option><option value="scooter">Scooter</option><option value="bicycle">Bicycle</option><option value="ev">EV</option>
              </select>
            </div>
            <div className="card partners-table-wrap">
              <table className="partners-table">
                <thead><tr><th>Partner</th><th>Contact &amp; Hub</th><th>Vehicle</th><th>Status</th><th>Deliveries &amp; Earnings</th><th>Wallet</th><th>Verification</th><th>Actions</th></tr></thead>
                <tbody>
                  {pageRows.length === 0 ? <tr><td colSpan={8} className="muted" style={{ textAlign: 'center', padding: 32 }}>No partners match this filter.</td></tr> : pageRows.map((p) => {
                    const veh = vehicleTag(p.vehicle_type); const ver = verificationMeta(p.approval_status); const st = fleetStatus(p);
                    return (
                      <tr key={p.rider_id} className="clickable" onClick={() => navigate(`/partners/${p.rider_id}`)} style={{ cursor: 'pointer' }}>
                        <td><div className="partner-cell"><div className="lt-avatar sm">{initials(p.full_name)}</div><div><div className="partner-name">{p.full_name}</div><div className="partner-meta">{partnerId(p)} · <span className="lt-rating">★ {p.rating != null ? p.rating.toFixed(1) : '—'}</span></div></div></div></td>
                        <td><div className="partner-phone">{p.phone ?? '—'}</div><div className="muted partner-hub">{p.operating_hub || 'Unassigned hub'}</div></td>
                        <td><div className="partner-vehicle">{p.vehicle_model || p.vehicle_type}</div><div className="muted">{p.vehicle_number}</div><span className={`veh-tag ${veh.cls}`}>{veh.label}</span></td>
                        <td><span className={`fleet-pill ${st.cls}`}>{st.label}</span>{st.sub && <div className="muted fleet-sub">{st.sub}</div>}</td>
                        <td><div><strong>{p.total_deliveries}</strong> <span className="muted">Total Trips</span></div><div className="partner-earn">{money(p.week_earnings_cents)} <span className="muted">this week</span></div></td>
                        <td><div className="partner-wallet">{money(p.wallet_balance_cents)}</div><div className={`wallet-tag ${p.payout_pending ? 'pending' : 'settled'}`}>{p.payout_pending ? 'Payout Pending' : 'Settled weekly'}</div></td>
                        <td><span className={`ver-pill ${ver.cls}`}>{ver.label}</span></td>
                        <td onClick={(e) => e.stopPropagation()}><div className="partner-actions"><button type="button" className="btn primary xs" onClick={() => navigate(`/partners/${p.rider_id}`)}>View</button>{['submitted', 'under_review', 'pending'].includes(p.approval_status) && <button type="button" className="btn warn xs" onClick={() => navigate('/verification')}>Verify</button>}{!p.account_active && <button type="button" className="btn ghost xs" onClick={() => navigate(`/partners/${p.rider_id}`)}>Audit</button>}</div></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="partners-footer">
                <span className="muted">Showing {filtered.length === 0 ? 0 : safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} of {filtered.length} partners</span>
                <div className="pagination">
                  <button type="button" className="page-btn" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>‹</button>
                  {Array.from({ length: Math.min(pageCount, 5) }, (_, i) => i).map((i) => <button key={i} type="button" className={`page-btn ${safePage === i ? 'active' : ''}`} onClick={() => setPage(i)}>{i + 1}</button>)}
                  <button type="button" className="page-btn" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>›</button>
                </div>
              </div>
            </div>
          </>
        )}
      </AsyncView>
    </div>
  );
}
