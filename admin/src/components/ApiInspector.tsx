import { useState, useSyncExternalStore } from 'react';
import { clearApiLog, getApiLog, subscribeApiLog, type ApiLogEntry } from '@/api/api-log';
import { useAuth } from '@/auth/AuthContext';
import { config } from '@/config';
import { ORDERS_ENDPOINTS } from '@/lib/orders-endpoints';

/** Renders the toggle + panel only for a super_admin when the env flag is on. */
export function ApiInspector() {
  const { me } = useAuth();
  const [open, setOpen] = useState(false);

  const allowed = config.showApiInspector && me?.admin_role === 'super_admin';
  if (!allowed) return null;

  return (
    <>
      <button
        type="button"
        className="btn sm api-inspector-toggle"
        onClick={() => setOpen((v) => !v)}
        title="Developer API inspector (super admin)"
      >
        {open ? '✕ API' : '⚡ API'}
      </button>
      {open && <InspectorPanel onClose={() => setOpen(false)} />}
    </>
  );
}

function InspectorPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<'live' | 'reference'>('live');
  const entries = useSyncExternalStore(subscribeApiLog, getApiLog);

  return (
    <div className="api-inspector-panel">
      <div className="pageheader" style={{ padding: '12px 14px', borderBottom: '1px solid #e5e7eb' }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>API inspector</h3>
        <button className="btn ghost sm" onClick={onClose}>Close</button>
      </div>

      <div className="row" style={{ padding: '10px 14px 0', gap: 8 }}>
        <button className={`btn sm ${tab === 'live' ? '' : 'secondary'}`} onClick={() => setTab('live')}>
          Live ({entries.length})
        </button>
        <button className={`btn sm ${tab === 'reference' ? '' : 'secondary'}`} onClick={() => setTab('reference')}>
          Reference
        </button>
        {tab === 'live' && entries.length > 0 && (
          <button className="btn danger sm" style={{ marginLeft: 'auto' }} onClick={clearApiLog}>Clear</button>
        )}
      </div>

      <div style={{ padding: 14, overflow: 'auto', flex: 1 }}>
        {tab === 'live' ? <LiveTab entries={entries} /> : <ReferenceTab />}
      </div>
    </div>
  );
}

function LiveTab({ entries }: { entries: ApiLogEntry[] }) {
  if (entries.length === 0) {
    return <p className="muted" style={{ fontSize: 13 }}>No API calls captured yet. Interact with the page to record requests.</p>;
  }
  return (
    <div>
      {entries.map((e) => (
        <LiveRow key={e.id} entry={e} />
      ))}
    </div>
  );
}

function statusColor(e: ApiLogEntry): string {
  if (!e.ok) return '#ef4444';
  return '#16a34a';
}

function LiveRow({ entry }: { entry: ApiLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card" style={{ marginBottom: 8, padding: 10 }}>
      <div
        className="clickable"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div style={{ fontSize: 12, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <span style={{ fontWeight: 700 }}>{entry.method}</span> {entry.path}
        </div>
        <span style={{ color: statusColor(entry), fontWeight: 700, fontSize: 12, flexShrink: 0 }}>
          {entry.error ? 'ERR' : entry.status}
        </span>
      </div>
      <div className="muted" style={{ fontSize: 11 }}>
        {new Date(entry.timestamp).toLocaleTimeString()} · {entry.durationMs}ms
      </div>
      {expanded && (
        <div style={{ marginTop: 8 }}>
          {entry.requestBody !== undefined && (
            <JsonBlock label="Request body" value={entry.requestBody} />
          )}
          {entry.error
            ? <JsonBlock label="Error" value={entry.error} />
            : <JsonBlock label="Response body" value={entry.responseBody} />}
        </div>
      )}
    </div>
  );
}

function ReferenceTab() {
  return (
    <div>
      <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
        Endpoints the Orders page calls. Paths are relative to <code>/api/v1</code>.
      </p>
      {ORDERS_ENDPOINTS.map((ep, i) => (
        <div key={i} className="card" style={{ marginBottom: 8, padding: 10 }}>
          <div style={{ fontSize: 12, fontFamily: 'monospace' }}>
            <span style={{ fontWeight: 700 }}>{ep.method}</span> {ep.path}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{ep.description}</div>
          {ep.requestExample !== undefined && <JsonBlock label="Example body" value={ep.requestExample} />}
        </div>
      ))}
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <div style={{ marginTop: 6 }}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{label}</div>
      <pre
        style={{
          margin: 0,
          padding: 8,
          background: '#0f172a',
          color: '#e2e8f0',
          borderRadius: 6,
          fontSize: 11,
          maxHeight: 220,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {text ?? 'null'}
      </pre>
    </div>
  );
}
