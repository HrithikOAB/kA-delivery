import { useEffect, useMemo, useState } from 'react';
import { api } from '@/api/client';
import { config } from '@/config';
import { useAsync } from '@/hooks/useAsync';
import { AsyncView } from '@/ui/kit';
import { MapView, type MapMarker } from '@/components/MapView';
import type { ActiveDelivery, PartnerListItem } from '@/api/types';

type StatusFilter = 'all' | 'pickup' | 'transit' | 'critical';
type MapTab = 'dispatch' | 'heatmap' | 'ev';

const CLUSTERS = [
  'Bengaluru — Koramangala / HSR / Indiranagar',
  'Bengaluru — Whitefield / Marathahalli',
  'Bengaluru — Jayanagar / BTM',
];

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');
}

function riderCode(id: number | null) {
  if (!id) return 'DM-—';
  return `DM-${String(id).padStart(4, '0')}`;
}

function isPickupPhase(status: string) {
  return ['preparing', 'ready', 'accepted', 'assigned'].includes(status);
}

function isTransitPhase(status: string) {
  return ['picked_up', 'out_for_delivery'].includes(status);
}

function isCritical(d: ActiveDelivery) {
  return Boolean(d.rider_marker?.is_stale) || (d.eta_minutes != null && d.eta_minutes > 45);
}

function riderStatus(d: ActiveDelivery) {
  if (isCritical(d)) return { label: 'Delayed', cls: 'lt-pill-danger' };
  if (isTransitPhase(d.order_status)) return { label: 'Fast Transit', cls: 'lt-pill-mint' };
  if (['preparing', 'ready', 'accepted'].includes(d.order_status)) return { label: 'At Restaurant', cls: 'lt-pill-orange' };
  if (d.order_status === 'assigned') return { label: 'On Track', cls: 'lt-pill-ok' };
  return { label: d.order_status.replace(/_/g, ' '), cls: 'lt-pill-muted' };
}

function etaLabel(d: ActiveDelivery) {
  if (d.eta_minutes == null) return 'ETA updating';
  const mins = Math.max(1, Math.round(d.eta_minutes));
  const km = d.distance_km != null ? `${d.distance_km.toFixed(1)} km` : '';
  return `${mins} mins left${km ? ` · ${km}` : ''}`;
}

function speedKmh(speed: number | null | undefined) {
  if (speed == null) return '—';
  const kmh = speed > 25 ? Math.round(speed) : Math.round(speed * 3.6);
  return `${kmh} km/h`;
}

function batteryPct(riderId: number | null) {
  if (!riderId) return 78;
  return 58 + (riderId % 35);
}

interface RiderCard {
  key: string;
  delivery: ActiveDelivery | null;
  partner: PartnerListItem | null;
  idle: boolean;
}

export function Operations() {
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [cluster, setCluster] = useState(CLUSTERS[0]);
  const [mapTab, setMapTab] = useState<MapTab>('dispatch');
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const { data: deliveries, loading, error, stale, reload } = useAsync(
    // Include test orders too — they flow through the real dispatch/tracking
    // pipeline, so Live Tracking must show them (passing `false` hid every
    // test delivery, leaving the map and stage filters empty).
    () => api.activeDeliveries(),
    [],
    config.liveTrackingPollMs,
  );
  const { data: overview } = useAsync(() => api.overview(), [], 15000);
  const { data: onlinePartners } = useAsync(() => api.partners({ online: true }), [], config.liveTrackingPollMs);

  const cards = useMemo(() => {
    const rows = deliveries ?? [];
    const partners = onlinePartners?.items ?? [];
    const busyRiderIds = new Set(rows.map((d) => d.rider_id).filter(Boolean) as number[]);
    const list: RiderCard[] = rows.map((d) => ({
      key: `order-${d.order_id}`,
      delivery: d,
      partner: partners.find((p) => p.rider_id === d.rider_id) ?? null,
      idle: false,
    }));
    for (const p of partners) {
      if (busyRiderIds.has(p.rider_id)) continue;
      list.push({ key: `idle-${p.rider_id}`, delivery: null, partner: p, idle: true });
    }
    return list;
  }, [deliveries, onlinePartners]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cards.filter((c) => {
      const d = c.delivery;
      if (filter === 'pickup' && (!d || !isPickupPhase(d.order_status))) return false;
      if (filter === 'transit' && (!d || !isTransitPhase(d.order_status))) return false;
      if (filter === 'critical' && (!d || !isCritical(d))) return false;
      if (filter !== 'all' && c.idle) return false;
      if (!q) return true;
      const name = (d?.rider_name ?? c.partner?.full_name ?? '').toLowerCase();
      const id = riderCode(d?.rider_id ?? c.partner?.rider_id ?? null).toLowerCase();
      const order = d ? String(d.order_id) : '';
      return name.includes(q) || id.includes(q) || order.includes(q);
    });
  }, [cards, filter, query]);

  const effectiveSelectedKey = filtered.some((c) => c.key === selectedKey) ? selectedKey : null;
  const selected = filtered.find((c) => c.key === effectiveSelectedKey) ?? null;
  const selDelivery = selected?.delivery ?? null;

  useEffect(() => {
    if (effectiveSelectedKey !== selectedKey) setSelectedKey(effectiveSelectedKey);
  }, [effectiveSelectedKey, selectedKey]);

  const onTrips = (deliveries ?? []).length;
  const online = overview?.metrics.online_partners ?? onlinePartners?.total ?? onTrips;
  const idle = Math.max(0, online - onTrips);
  const criticalCount = (deliveries ?? []).filter(isCritical).length;
  const pickupCount = (deliveries ?? []).filter((d) => isPickupPhase(d.order_status)).length;
  const transitCount = (deliveries ?? []).filter((d) => isTransitPhase(d.order_status)).length;

  const visibleOrderIds = useMemo(() => {
    const ids = new Set<number>();
    for (const c of filtered) {
      if (c.delivery) ids.add(c.delivery.order_id);
    }
    return ids;
  }, [filtered]);

  const [fitSnapshot, setFitSnapshot] = useState<{ key: string; points: [number, number][] } | null>(null);

  const visibleIdleRiderIds = useMemo(() => {
    const ids = new Set<number>();
    for (const c of filtered) {
      if (c.idle && c.partner) ids.add(c.partner.rider_id);
    }
    return ids;
  }, [filtered]);

  useEffect(() => {
    if (!effectiveSelectedKey || !selected) {
      setFitSnapshot(null);
      return;
    }
    if (selDelivery) {
      const pts: [number, number][] = [[selDelivery.pickup_lat, selDelivery.pickup_lng]];
      if (selDelivery.rider_marker) {
        pts.push([selDelivery.rider_marker.lat, selDelivery.rider_marker.lng]);
      }
      pts.push([selDelivery.dropoff_lat, selDelivery.dropoff_lng]);
      setFitSnapshot({ key: effectiveSelectedKey, points: pts });
      return;
    }
    if (selected.idle && selected.partner?.last_lat != null && selected.partner?.last_lng != null) {
      setFitSnapshot({
        key: effectiveSelectedKey,
        points: [[selected.partner.last_lat, selected.partner.last_lng]],
      });
    }
  }, [effectiveSelectedKey, selDelivery, selected]);

  const markers: MapMarker[] = useMemo(() => {
    const list: MapMarker[] = [];
    for (const d of deliveries ?? []) {
      if (!visibleOrderIds.has(d.order_id)) continue;
      const isSel = selDelivery?.order_id === d.order_id;
      list.push({
        id: `pickup-${d.order_id}`,
        lat: d.pickup_lat,
        lng: d.pickup_lng,
        label: d.pickup_label ?? 'Pickup',
        kind: 'pickup',
      });
      list.push({
        id: `drop-${d.order_id}`,
        lat: d.dropoff_lat,
        lng: d.dropoff_lng,
        label: d.dropoff_text,
        kind: 'dropoff',
      });
      if (d.rider_marker) {
        list.push({
          id: `rider-${d.order_id}`,
          lat: d.rider_marker.lat,
          lng: d.rider_marker.lng,
          label: d.rider_name ?? 'Rider',
          kind: 'rider',
          stale: d.rider_marker.is_stale,
          selected: isSel,
        });
      }
    }
    const busyRiderIds = new Set((deliveries ?? []).map((d) => d.rider_id).filter(Boolean) as number[]);
    for (const p of onlinePartners?.items ?? []) {
      if (busyRiderIds.has(p.rider_id)) continue;
      if (!visibleIdleRiderIds.has(p.rider_id)) continue;
      if (p.last_lat == null || p.last_lng == null) continue;
      list.push({
        id: `idle-${p.rider_id}`,
        lat: p.last_lat,
        lng: p.last_lng,
        label: p.full_name,
        kind: 'idle',
        stale: p.location_is_stale,
        selected: selected?.partner?.rider_id === p.rider_id && selected.idle,
      });
    }
    return list;
  }, [deliveries, selDelivery, visibleOrderIds, onlinePartners, visibleIdleRiderIds, selected]);

  const route = useMemo(() => {
    if (!selDelivery) return undefined;
    const pts: [number, number][] = [[selDelivery.pickup_lat, selDelivery.pickup_lng]];
    if (selDelivery.rider_marker) {
      pts.push([selDelivery.rider_marker.lat, selDelivery.rider_marker.lng]);
    }
    pts.push([selDelivery.dropoff_lat, selDelivery.dropoff_lng]);
    return pts;
  }, [selDelivery]);

  const mapFit = useMemo(() => {
    if (fitSnapshot) return fitSnapshot;
    if (markers.length === 0) return null;
    return {
      key: 'overview',
      points: markers.map((m) => [m.lat, m.lng] as [number, number]),
    };
  }, [fitSnapshot, markers]);

  return (
    <div className="live-tracking">
      <div className="lt-toolbar">
        <div className="lt-stats">
          <strong>{online} Partners Online</strong>
          <span className="lt-stat-sub">({onTrips} On Trips, {idle} Idle)</span>
          {stale && <span className="lt-refresh-hint">Refreshing…</span>}
        </div>
        <div className="lt-filters">
          <button type="button" className={`lt-chip ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
            All Active ({onTrips})
          </button>
          <button type="button" className={`lt-chip ${filter === 'pickup' ? 'active' : ''}`} onClick={() => setFilter('pickup')}>
            In Pickup ({pickupCount})
          </button>
          <button type="button" className={`lt-chip ${filter === 'transit' ? 'active' : ''}`} onClick={() => setFilter('transit')}>
            In Transit ({transitCount})
          </button>
          <button type="button" className={`lt-chip lt-chip-danger ${filter === 'critical' ? 'active' : ''}`} onClick={() => setFilter('critical')}>
            Critical Delays ({criticalCount})
          </button>
        </div>
        <select className="lt-cluster" value={cluster} onChange={(e) => setCluster(e.target.value)} aria-label="Cluster">
          {CLUSTERS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <AsyncView
        data={deliveries}
        loading={loading}
        error={error}
        onRetry={reload}
        stale={stale}
        isEmpty={(d) => d.length === 0 && (onlinePartners?.items.length ?? 0) === 0}
        emptyTitle="No partners online right now"
      >
        {() => (
          <div className="lt-grid">
            <aside className="lt-list-panel">
              <div className="lt-search-wrap">
                <input
                  className="lt-search"
                  placeholder="Filter by Rider name, ID, or Order #…"
                  aria-label="Filter riders"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="lt-cards">
                {filtered.length === 0 ? (
                  <div className="lt-empty">No riders match this filter.</div>
                ) : (
                  filtered.map((c) => (
                    <PartnerCard
                      key={c.key}
                      card={c}
                      active={selectedKey === c.key}
                      onSelect={() => setSelectedKey(c.key)}
                    />
                  ))
                )}
              </div>
            </aside>

            <section className="lt-map-panel">
              <div className="lt-map-tabs">
                {([
                  ['dispatch', 'Dispatch View'],
                  ['heatmap', 'Heatmap & Congestion'],
                  ['ev', 'EV Stations'],
                ] as [MapTab, string][]).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={`lt-map-tab ${mapTab === id ? 'active' : ''}`}
                    onClick={() => setMapTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="lt-map-frame">
                {mapTab === 'dispatch' ? (
                  <>
                    {online > 0 &&
                      markers.filter((m) => m.kind === 'idle' || m.kind === 'rider').length === 0 && (
                        <div className="dm-map-banner">
                          Waiting for GPS from online partners — open the partner app, go online, and allow location.
                        </div>
                      )}
                    <MapView
                      markers={markers}
                      height={560}
                      route={route}
                      fitPoints={mapFit?.points}
                      fitKey={mapFit?.key ?? null}
                    />
                  </>
                ) : (
                  <div className="lt-map-placeholder">
                    <p>{mapTab === 'heatmap' ? 'Heatmap & congestion layers' : 'EV charging stations'}</p>
                    <span className="muted">Coming soon for this cluster</span>
                  </div>
                )}
                <div className="lt-legend">
                  <span><i className="dot purple" /> Assigned / Active Route</span>
                  <span><i className="dot indigo" /> Idle (Available)</span>
                  <span><i className="dot mint" /> On Delivery</span>
                </div>
              </div>

              {selDelivery && (
                <FloatingDetail delivery={selDelivery} partner={selected?.partner ?? null} />
              )}
            </section>
          </div>
        )}
      </AsyncView>
    </div>
  );
}

function PartnerCard({ card, active, onSelect }: { card: RiderCard; active: boolean; onSelect: () => void }) {
  const d = card.delivery;
  const name = d?.rider_name ?? card.partner?.full_name ?? 'Partner';
  const riderId = d?.rider_id ?? card.partner?.rider_id ?? null;
  const status = d ? riderStatus(d) : { label: 'Idle (Ready)', cls: 'lt-pill-muted' };

  return (
    <button type="button" className={`lt-card ${active ? 'active' : ''}`} onClick={onSelect}>
      <div className="lt-card-top">
        <div className="lt-avatar">{initials(name)}</div>
        <div className="lt-card-meta">
          <div className="lt-card-name">{name}</div>
          <div className="lt-card-sub">
            {riderCode(riderId)} · Scooter · <span className="lt-rating">★ 4.9</span>
          </div>
        </div>
        <span className={`lt-pill ${status.cls}`}>{status.label}</span>
      </div>
      {d ? (
        <div className="lt-card-trip">
          <div className="lt-trip-head">
            <span>Trip #{d.order_id}</span>
            <span className="lt-trip-eta">{etaLabel(d)}</span>
          </div>
          <div className="lt-trip-loc">
            <span className="lt-loc pickup">{d.pickup_label ?? 'Pickup point'}</span>
            <span className="lt-loc drop">{d.dropoff_text}</span>
          </div>
        </div>
      ) : (
        <div className="lt-card-trip muted">Available for dispatch</div>
      )}
    </button>
  );
}

function FloatingDetail({ delivery: d, partner }: { delivery: ActiveDelivery; partner: PartnerListItem | null }) {
  const status = riderStatus(d);
  const marker = d.rider_marker;
  const mins = d.eta_minutes != null ? Math.max(1, Math.round(d.eta_minutes)) : null;

  return (
    <div className="lt-float">
      <div className="lt-float-head">
        <div className="lt-avatar lg">{initials(d.rider_name ?? 'R')}</div>
        <div>
          <div className="lt-float-name">{d.rider_name ?? 'Rider'} <span className="muted">{riderCode(d.rider_id)}</span></div>
          <div className="lt-float-vehicle">Scooter{d.is_test ? ' · TEST' : ''}</div>
        </div>
      </div>
      <div className="lt-metrics">
        <div><span>Speed</span><strong>{speedKmh(marker?.speed)}</strong></div>
        <div><span>Battery (est.)</span><strong>{batteryPct(d.rider_id)}%</strong></div>
        <div><span>Remaining</span><strong>{mins != null ? `${mins} mins` : '—'}</strong></div>
      </div>
      <div className="lt-float-trip">
        <div className="lt-float-trip-label">
          ACTIVE TRIP #{d.order_id}
          <span className={`lt-pill ${status.cls}`}>{isTransitPhase(d.order_status) ? 'In Transit' : status.label}</span>
        </div>
        <div className="lt-float-route">
          <div><em>Picked from</em>{d.pickup_label ?? '—'}</div>
          <div><em>Drop point</em>{d.dropoff_text}</div>
        </div>
        {partner?.phone && (
          <div className="lt-float-contact muted">Courier · {partner.phone}</div>
        )}
      </div>
      <div className="lt-float-actions">
        <button type="button" className="btn-secondary" disabled title="Coming soon">Reassign Partner</button>
        {partner?.phone ? (
          <a className="btn-primary" href={`tel:${partner.phone}`}>
            <PhoneIcon /> Call Courier
          </a>
        ) : (
          <button type="button" className="btn-primary" disabled>
            <PhoneIcon /> Call Courier
          </button>
        )}
      </div>
    </div>
  );
}

function PhoneIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6.6 10.8a15 15 0 006.6 6.6l2.2-2.2a1 1 0 001-.24 11.5 11.5 0 003.6.6 1 1 0 011 1V20a1 1 0 01-1 1A17 17 0 013 5a1 1 0 011-1h3.5a1 1 0 011 1 11.5 11.5 0 00.6 3.6 1 1 0 01-.24 1L6.6 10.8z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
