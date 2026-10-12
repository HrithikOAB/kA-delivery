import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { AsyncView } from '@/ui/kit';
import { formatGmv, money, orderStatusMeta } from '@/theme';
import type { ActiveDelivery, OrderSummary } from '@/api/types';

const PAGE_SIZE = 6;

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');
}

function statusPill(status: string) {
  const meta = orderStatusMeta[status] ?? { label: status.replace(/_/g, ' '), cls: 'status-muted' };
  return <span className={`status-pill ${meta.cls}`}>{meta.label}</span>;
}

function LiveOrderRow({
  d,
  order,
  onTrack,
}: {
  d: ActiveDelivery;
  order?: OrderSummary;
  onTrack: () => void;
}) {
  const customer = order?.customer_name ?? d.dropoff_text?.split(',')[0] ?? 'Customer';
  const pickup = d.pickup_label ?? order?.mess_name ?? 'Pickup';
  const amount = order?.total_cents ?? 0;
  const orderLabel = order?.external_order_ref ?? `#${d.order_id}`;

  return (
    <tr className="live-row">
      <td><strong className="order-id">{orderLabel}</strong></td>
      <td>
        <div className="cell-primary">{customer}</div>
        <div className="cell-muted">{d.dropoff_text?.slice(0, 32) ?? '—'}</div>
      </td>
      <td><div className="cell-primary">{pickup}</div></td>
      <td>
        <div className="courier-cell">
          <span className="courier-avatar">{d.rider_name ? initials(d.rider_name) : '—'}</span>
          <span>{d.rider_name ?? 'Unassigned'}</span>
        </div>
      </td>
      <td><strong>{amount ? money(amount) : '—'}</strong></td>
      <td>{statusPill(d.order_status)}</td>
      <td>
        <button className="btn secondary sm" type="button" onClick={onTrack}>Track</button>
      </td>
    </tr>
  );
}

export function Overview() {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);

  const { data, loading, error, stale, reload } = useAsync(
    async () => {
      const [overview, live, ordersPage] = await Promise.all([
        api.overview(),
        api.activeDeliveries(),
        api.orders(),
      ]);
      const orderMap = new Map(ordersPage.items.map((o) => [o.order_id, o]));
      return { overview, live, orderMap };
    },
    [],
    15000,
  );

  const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <div className="content dashboard">
      <AsyncView data={data} loading={loading} error={error} onRetry={reload} stale={stale}>
        {({ overview, live, orderMap }) => {
          const m = overview.metrics;
          const fleetPct = m.approved_partners
            ? Math.round((m.online_partners / m.approved_partners) * 100)
            : 0;
          const liveTotal = m.live_kitchen + m.live_picked_up + m.live_en_route;
          const pageCount = Math.max(1, Math.ceil(live.length / PAGE_SIZE));
          const safePage = Math.min(page, pageCount - 1);
          const pageRows = live.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

          return (
            <>
              <div className="dispatch-head">
                <div>
                  <h1 className="dispatch-title">Operations dashboard</h1>
                  <p className="muted dispatch-sub">Live orders, fleet status, and partner verification</p>
                </div>
                <div className="dispatch-actions">
                  <button className="btn secondary sm" type="button" onClick={() => navigate('/operations')}>Live tracking</button>
                  <button className="btn secondary sm" type="button" onClick={() => navigate('/orders')}>Orders</button>
                  <span className="date-pill">Today, {today}</span>
                </div>
              </div>

              <div className="kpi-grid">
                <div className="kpi-card kpi-purple">
                  <span className="kpi-label">Orders today</span>
                  <div className="kpi-value">{m.orders_today.toLocaleString('en-IN')}</div>
                  <div className="kpi-sub muted">GMV {formatGmv(m.gmv_today_cents)}</div>
                </div>

                <div className="kpi-card kpi-green">
                  <span className="kpi-label">Active deliveries</span>
                  <div className="kpi-value">{liveTotal}</div>
                  <div className="kpi-chips">
                    <span className="chip">{m.live_kitchen} preparing</span>
                    <span className="chip">{m.live_picked_up} picked up</span>
                    <span className="chip">{m.live_en_route} en route</span>
                  </div>
                </div>

                <div className="kpi-card kpi-neutral">
                  <span className="kpi-label">Fleet online</span>
                  <div className="kpi-value">{m.online_partners}<span className="kpi-denom">/{m.approved_partners}</span></div>
                  <div className="fleet-bar"><div className="fleet-fill" style={{ width: `${fleetPct}%` }} /></div>
                  <div className="kpi-sub muted">{fleetPct}% of approved partners</div>
                </div>

                <div className="kpi-card kpi-yellow">
                  <span className="kpi-label">Pending verifications</span>
                  <div className="kpi-value">{m.pending_applications}</div>
                  <div className="kpi-sub">
                    <button className="link-btn" type="button" onClick={() => navigate('/verification')}>
                      Review applications →
                    </button>
                  </div>
                </div>
              </div>

              <div className="card live-stream">
                <div className="card-head">
                  <h3>Active deliveries</h3>
                  <button className="btn ghost sm" type="button" onClick={() => navigate('/operations')}>Open map →</button>
                </div>
                {live.length === 0 ? (
                  <p className="muted empty-copy">No active deliveries right now.</p>
                ) : (
                  <>
                    <div className="table-wrap">
                      <table className="live-table">
                        <thead>
                          <tr>
                            <th>Order</th>
                            <th>Customer</th>
                            <th>Pickup</th>
                            <th>Courier</th>
                            <th>Amount</th>
                            <th>Status</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pageRows.map((d) => (
                            <LiveOrderRow
                              key={d.order_id}
                              d={d}
                              order={orderMap.get(d.order_id)}
                              onTrack={() => navigate('/operations')}
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="table-footer">
                      <span className="muted">Showing {safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, live.length)} of {live.length}</span>
                      <div className="pager">
                        <button type="button" className="btn secondary sm" disabled={safePage === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Prev</button>
                        <span>{safePage + 1} / {pageCount}</span>
                        <button type="button" className="btn secondary sm" disabled={safePage >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>Next</button>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div className="dashboard-row bottom-row">
                <div className="card payout-card">
                  <div className="card-head"><h3>Recent verification applications</h3></div>
                  {overview.recent_applications.length === 0 ? (
                    <p className="muted empty-copy">No pending applications.</p>
                  ) : (
                    <div className="payout-list">
                      {overview.recent_applications.map((a) => (
                        <div key={a.rider_id} className="payout-row">
                          <span className="payout-avatar">{initials(a.full_name)}</span>
                          <div className="payout-meta">
                            <strong>{a.full_name}</strong>
                            <span className="muted">{a.vehicle_type} · {a.phone ?? a.email ?? 'Partner'}</span>
                          </div>
                          <div className="payout-actions">
                            <button className="btn secondary sm" type="button" onClick={() => navigate('/verification')}>Review</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="card leaders-card">
                  <div className="card-head"><h3>Top partners (deliveries)</h3></div>
                  {overview.fleet_leaders.length === 0 ? (
                    <p className="muted empty-copy">No delivery data yet.</p>
                  ) : (
                    <div className="leader-list">
                      {overview.fleet_leaders.map((l, i) => (
                        <div key={l.rider_id} className="leader-row">
                          <span className={`rank rank-${i + 1}`}>{i + 1}</span>
                          <div className="leader-info">
                            <span className="leader-name">{l.full_name}</span>
                            <span className="muted">{l.total_deliveries} deliveries · {l.is_online ? 'online' : 'offline'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}
