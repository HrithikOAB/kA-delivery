import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { Page } from '@/components/Layout';
import { MapView, type MapMarker } from '@/components/MapView';
import { ApiInspector } from '@/components/ApiInspector';
import { fetchRoadRoute } from '@/lib/directions';
import { money } from '@/theme';
import type { CandidateRider, ExternalProvider, OrderDetail } from '@/api/types';

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const id = Number(orderId);
  const [o, setO] = useState<OrderDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState('');

  const load = () => api.order(id).then(setO).catch((e) => setErr(e.message));
  useEffect(() => { setO(null); setErr(null); void load(); /* eslint-disable-next-line */ }, [id]);

  const back = <button className="btn ghost sm" onClick={() => navigate('/orders')}>← Back to orders</button>;

  if (Number.isNaN(id)) return <Page title="Order" action={back}><p className="muted">Invalid order id.</p></Page>;

  const markers: MapMarker[] = o
    ? [
        ...(o.mess ? [{ lat: o.mess.lat, lng: o.mess.lng, kind: 'pickup' as const, label: o.mess.name }] : []),
        ...(o.customer ? [{ lat: o.customer.dropoff_lat, lng: o.customer.dropoff_lng, kind: 'dropoff' as const, label: 'Drop-off' }] : []),
      ]
    : [];
  const fitPoints: [number, number][] = markers.map((m) => [m.lat, m.lng]);

  // Pickup (mess) → drop-off (customer) for the route line.
  const pickup = o?.mess ? { lat: o.mess.lat, lng: o.mess.lng } : null;
  const dropoff = o?.customer ? { lat: o.customer.dropoff_lat, lng: o.customer.dropoff_lng } : null;
  const straightLine = useMemo<[number, number][]>(
    () => (pickup && dropoff ? [[pickup.lat, pickup.lng], [dropoff.lat, dropoff.lng]] : []),
    [pickup?.lat, pickup?.lng, dropoff?.lat, dropoff?.lng],
  );
  // <GoogleMap> center is controlled, so it must sit near the markers or it
  // overrides fitBounds and the markers render off-screen. Use the midpoint.
  const mapCenter = useMemo<[number, number] | undefined>(() => {
    if (fitPoints.length === 0) return undefined;
    const lat = fitPoints.reduce((s, p) => s + p[0], 0) / fitPoints.length;
    const lng = fitPoints.reduce((s, p) => s + p[1], 0) / fitPoints.length;
    return [lat, lng];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(fitPoints)]);
  const [roadRoute, setRoadRoute] = useState<[number, number][] | null>(null);
  useEffect(() => {
    if (!pickup || !dropoff) { setRoadRoute(null); return; }
    const controller = new AbortController();
    void fetchRoadRoute(pickup, dropoff, controller.signal).then((res) => {
      setRoadRoute(res && res.points.length > 1 ? res.points : null);
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickup?.lat, pickup?.lng, dropoff?.lat, dropoff?.lng]);

  return (
    <Page
      title={o ? `Order #${o.order_id}` : `Order #${id}`}
      action={back}
    >
      {err && <div className="card" style={{ background: '#fee2e2', marginBottom: 12 }}>{err}</div>}
      {!o ? <p>Loading…</p> : (
        <>
          <div className="pageheader" style={{ marginBottom: 12 }}>
            <div>
              {o.is_test && <span className="badge test">TEST</span>}{' '}
              <span className="muted">{o.status}{o.delivery_status ? ` / ${o.delivery_status}` : ''}</span>
            </div>
            <span className="muted">{new Date(o.created_at).toLocaleString()}</span>
          </div>

          {markers.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <MapView markers={markers} height={260} center={mapCenter} fitPoints={fitPoints} fitKey={`order-${o.order_id}`} route={roadRoute ?? straightLine} />
            </div>
          )}

          <div className="row" style={{ alignItems: 'flex-start', gap: 12 }}>
            <div className="card" style={{ flex: 1 }}>
              <h4 style={{ marginTop: 0 }}>Mess (pickup)</h4>
              {o.mess ? (
                <div style={{ fontSize: 13 }}>
                  <div><strong>{o.mess.name}</strong></div>
                  <div className="muted">{o.mess.address_text || '—'}</div>
                  {o.mess.contact_phone && <div>☎ {o.mess.contact_phone}</div>}
                  <div className="muted" style={{ fontSize: 11 }}>{o.mess.lat.toFixed(5)}, {o.mess.lng.toFixed(5)}</div>
                </div>
              ) : <p className="muted">—</p>}
            </div>
            <div className="card" style={{ flex: 1 }}>
              <h4 style={{ marginTop: 0 }}>Customer (drop-off)</h4>
              {o.customer ? (
                <div style={{ fontSize: 13 }}>
                  <div><strong>{o.customer.name || '—'}</strong></div>
                  {o.customer.phone && <div>☎ {o.customer.phone}</div>}
                  <div className="muted">{o.customer.dropoff_text}</div>
                  {o.customer.note && <div style={{ marginTop: 4 }}>Note: {o.customer.note}</div>}
                </div>
              ) : <p className="muted">—</p>}
            </div>
          </div>

          <h4>Items</h4>
          <div className="card" style={{ padding: 0 }}>
            <table style={{ fontSize: 13 }}>
              <thead><tr><th>Item</th><th>Qty</th><th style={{ textAlign: 'right' }}>Line</th></tr></thead>
              <tbody>
                {o.items.map((it, i) => (
                  <tr key={i}><td>{it.name}</td><td>× {it.quantity}</td><td style={{ textAlign: 'right' }}>{money(it.line_total_cents)}</td></tr>
                ))}
                {o.items.length === 0 && <tr><td colSpan={3} className="muted">No line items</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 13, marginTop: 6, textAlign: 'right' }}>
            <div className="muted">Subtotal {money(o.subtotal_cents)} · Delivery {money(o.delivery_fee_cents)} · Tax {money(o.tax_cents)}</div>
            <div><strong>Total {money(o.total_cents)}</strong> · {o.payment_method} ({o.payment_status})</div>
          </div>

          <AssignmentPanel order={o} onChanged={load} />

          <h4>Delivery timeline</h4>
          <div className="card" style={{ maxHeight: 220, overflow: 'auto' }}>
            {o.timeline.map((e) => (
              <div key={e.id} style={{ fontSize: 13, padding: '4px 0', borderBottom: '1px solid #f0f1f5' }}>
                <strong>{e.event_type}</strong>{' '}
                {e.from_state && <span className="muted">{e.from_state} → {e.to_state}</span>}
                {e.detail && <span className="muted"> · {e.detail}</span>}
                {e.reason && <div className="muted">“{e.reason}”</div>}
                <span className="muted" style={{ float: 'right', fontSize: 11 }}>{new Date(e.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
            {o.timeline.length === 0 && <p className="muted" style={{ margin: 8 }}>No events yet.</p>}
          </div>

          <h4>Reported issues ({o.issues.length})</h4>
          {o.issues.map((i) => (
            <div key={i.id} className="card" style={{ marginBottom: 8 }}>
              <div><strong>{i.issue_type}</strong> · <span className="muted">{i.status}</span></div>
              <div className="muted" style={{ fontSize: 13 }}>{i.note}</div>
              {i.admin_note && <div style={{ fontSize: 13 }}>Note: {i.admin_note}</div>}
              <div className="row" style={{ marginTop: 8 }}>
                <input placeholder="Add resolution note" value={note} onChange={(e) => setNote(e.target.value)} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb' }} />
                <button className="btn secondary sm" disabled={!note.trim()} onClick={async () => { await api.addIssueNote(i.id, note.trim()); setNote(''); void load(); }}>Add note</button>
                <button className="btn mint sm" onClick={async () => { await api.resolveIssue(i.id); void load(); }}>Resolve</button>
              </div>
            </div>
          ))}
          {o.issues.length === 0 && <p className="muted">None.</p>}
        </>
      )}
      <ApiInspector />
    </Page>
  );
}

const PROVIDERS: { value: ExternalProvider; label: string }[] = [
  { value: 'zomato', label: 'Zomato' },
  { value: 'swiggy', label: 'Swiggy' },
  { value: 'other', label: 'Other' },
];
const EXTERNAL_STEPS: ('assigned' | 'picked_up' | 'delivered')[] = ['assigned', 'picked_up', 'delivered'];

function AssignmentPanel({ order, onChanged }: { order: OrderDetail; onChanged: () => void }) {
  const terminal = order.status === 'delivered' || order.status === 'cancelled';
  const [mode, setMode] = useState<'ka' | 'external'>(order.fulfillment_type === 'external' ? 'external' : 'ka');
  const a = order.assignment;

  return (
    <div className="card" style={{ background: '#f7f8fc', marginTop: 12 }}>
      <div className="pageheader" style={{ marginBottom: 8 }}>
        <h4 style={{ margin: 0 }}>Delivery assignment</h4>
        {a?.rider_name && <span className="muted">Rider: {a.rider_name}{a.offer_pending ? ' (offer sent)' : ''}</span>}
        {order.fulfillment_type === 'external' && <span className="badge" style={{ background: '#fef3c7', color: '#d97706' }}>{(order.external_provider ?? 'EXTERNAL').toUpperCase()}</span>}
      </div>

      {terminal ? (
        <p className="muted" style={{ margin: 0 }}>Order is {order.status}; assignment is locked.</p>
      ) : (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            <button className={`btn sm ${mode === 'ka' ? '' : 'secondary'}`} onClick={() => setMode('ka')}>KA Delivery partner</button>
            <button className={`btn sm ${mode === 'external' ? 'mint' : 'secondary'}`} onClick={() => setMode('external')}>External platform</button>
          </div>
          {mode === 'ka' ? <KaAssign order={order} onChanged={onChanged} /> : <ExternalAssign order={order} onChanged={onChanged} />}
        </>
      )}
    </div>
  );
}

function KaAssign({ order, onChanged }: { order: OrderDetail; onChanged: () => void }) {
  const [data, setData] = useState<CandidateRider[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const loadCandidates = () => {
    setLoading(true);
    api.orderCandidates(order.order_id)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load partners'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { loadCandidates(); /* eslint-disable-next-line */ }, [order.order_id]);

  const offer = async (riderId: number) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      await api.assignOrder(order.order_id, { mode: 'internal', rider_id: riderId });
      setMsg('Offer sent — waiting for the partner to accept.');
      onChanged();
    } catch (e) { setErr(e instanceof Error ? e.message : 'Assign failed'); }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="muted" style={{ fontSize: 12 }}>Approved online partners, nearest to the mess first.</span>
        <button className="btn secondary sm" onClick={loadCandidates} disabled={loading}>Refresh</button>
      </div>
      {err && <div className="card" style={{ background: '#fee2e2', margin: '8px 0' }}>{err}</div>}
      {msg && <div className="card" style={{ background: '#dcfce7', margin: '8px 0' }}>{msg}</div>}
      {loading && !data && <p className="muted">Finding partners…</p>}
      {data && data.length === 0 && <p className="muted">No approved online partners right now.</p>}
      <div style={{ maxHeight: 260, overflow: 'auto', marginTop: 8 }}>
        {(data ?? []).map((r) => (
          <div key={r.rider_id} className="card" style={{ marginBottom: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center', opacity: r.available ? 1 : 0.6 }}>
            <div style={{ fontSize: 13 }}>
              <div>
                <span style={{ color: r.is_online ? '#16a34a' : '#9ca3af' }}>●</span>{' '}
                <strong>{r.full_name}</strong> · ⭐ {r.rating != null ? r.rating.toFixed(1) : '—'} · {r.vehicle_type}
              </div>
              <div className="muted">
                {r.distance_km != null ? `${r.distance_km.toFixed(2)} km from mess` : 'distance unknown'}
                {r.location_is_stale ? ' · location stale' : ''}
                {!r.available && r.unavailable_reason ? ` · ${r.unavailable_reason}` : ''}
              </div>
            </div>
            <button className="btn sm" disabled={busy || !r.available} onClick={() => offer(r.rider_id)}>Send offer</button>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExternalAssign({ order, onChanged }: { order: OrderDetail; onChanged: () => void }) {
  const [provider, setProvider] = useState<ExternalProvider>((order.external_provider as ExternalProvider) ?? 'zomato');
  const [reference, setReference] = useState(order.external_reference ?? '');
  const [note, setNote] = useState(order.external_note ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const isExternal = order.fulfillment_type === 'external';

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : 'Failed'); } finally { setBusy(false); }
  };

  return (
    <div>
      {err && <div className="card" style={{ background: '#fee2e2', marginBottom: 8 }}>{err}</div>}
      <div className="row">
        <div className="field"><label>Platform</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value as ExternalProvider)}>
            {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div className="field" style={{ flex: 1 }}><label>Reference / tracking id</label>
          <input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. ZOM-12345" />
        </div>
      </div>
      <div className="field"><label>Note</label><input value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <button className="btn mint sm" disabled={busy} onClick={() => act(() => api.assignOrder(order.order_id, { mode: 'external', provider, reference: reference.trim() || undefined, note: note.trim() || undefined }))}>
        {isExternal ? 'Update external delivery' : 'Mark as external delivery'}
      </button>

      {isExternal && (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Current status: <strong>{order.external_status ?? '—'}</strong></div>
          <div className="row">
            {EXTERNAL_STEPS.map((s) => (
              <button key={s} className={`btn sm ${order.external_status === s ? '' : 'secondary'}`} disabled={busy || order.external_status === s} onClick={() => act(() => api.setOrderExternalStatus(order.order_id, s))}>
                {s.replace('_', ' ')}
              </button>
            ))}
            <button className="btn danger sm" disabled={busy} onClick={() => act(() => api.setOrderExternalStatus(order.order_id, 'cancelled'))}>cancelled</button>
          </div>
        </div>
      )}
    </div>
  );
}
