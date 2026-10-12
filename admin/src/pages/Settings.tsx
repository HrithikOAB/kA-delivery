import { useState } from 'react';
import { api } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { useAsync } from '@/hooks/useAsync';
import { Page } from '@/components/Layout';
import { AsyncView } from '@/ui/kit';
import type { PartnerApiKey, PartnerApiKeySecret } from '@/api/types';

export function Settings() {
  const { me } = useAuth();
  return (
    <Page title="Settings">
      {me?.admin_role === 'super_admin'
        ? <ApiKeys />
        : <div className="card muted">Only a super admin can manage partner API keys.</div>}
    </Page>
  );
}

function fmt(ts: string | null) {
  return ts ? new Date(ts).toLocaleString() : '—';
}

function ApiKeys() {
  const { data, loading, error, stale, reload } = useAsync(() => api.apiKeys(), []);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<PartnerApiKeySecret | null>(null);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); await reload(); } catch (e) { setErr(e instanceof Error ? e.message : 'Failed'); } finally { setBusy(false); }
  };

  const create = () => act(async () => {
    setRevealed(await api.createApiKey(name.trim()));
    setName('');
  });
  const rotate = (k: PartnerApiKey) => {
    if (!window.confirm(`Rotate "${k.name}"? The current key stops working immediately.`)) return;
    void act(async () => setRevealed(await api.rotateApiKey(k.id)));
  };
  const revoke = (k: PartnerApiKey) => {
    if (!window.confirm(`Revoke "${k.name}"? The partner loses access immediately. This cannot be undone.`)) return;
    void act(() => api.revokeApiKey(k.id));
  };

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Partner API keys</h3>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          External partners send this key as the <code>X-API-Key</code> header to create orders
          (<code>POST /api/v1/partner/orders</code>) and track them (<code>POST /api/v1/partner/tracking</code>).
          Issue one key per partner. The full key is shown only once.
        </p>
        <div className="row" style={{ alignItems: 'flex-end', gap: 8 }}>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <label htmlFor="key-name">Partner name</label>
            <input id="key-name" value={name} maxLength={128} placeholder="e.g. MigoEats" onChange={(e) => setName(e.target.value)} />
          </div>
          <button className="btn" style={{ flex: '0 0 auto' }} disabled={busy || !name.trim()} onClick={create}>Generate key</button>
        </div>
      </div>

      {revealed && <RevealedKey secret={revealed} onDone={() => setRevealed(null)} />}
      {err && <div className="card" style={{ background: '#fee2e2', marginBottom: 12 }}>{err}</div>}

      <AsyncView data={data} loading={loading} error={error} onRetry={reload} stale={stale} isEmpty={(d) => d.length === 0} emptyTitle="No API keys yet. Generate one above to give a partner access.">
        {(keys) => (
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead><tr><th>Partner</th><th>Key</th><th>Status</th><th>Created</th><th>Last used</th><th /></tr></thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td><strong>{k.name}</strong>{k.rotated_at && <div className="muted" style={{ fontSize: 12 }}>Rotated {fmt(k.rotated_at)}</div>}</td>
                    <td><code>{k.key_prefix}…</code></td>
                    <td>
                      {k.is_active
                        ? <span className="badge" style={{ background: '#dcfce7', color: '#15803d' }}>Active</span>
                        : <span className="badge" style={{ background: '#f3f4f6', color: '#6b7280' }}>Revoked</span>}
                    </td>
                    <td className="muted">{fmt(k.created_at)}</td>
                    <td className="muted">{fmt(k.last_used_at)}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {k.is_active && (
                        <>
                          <button className="btn secondary sm" disabled={busy} onClick={() => rotate(k)}>Rotate</button>{' '}
                          <button className="btn danger sm" disabled={busy} onClick={() => revoke(k)}>Revoke</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>
    </div>
  );
}

function RevealedKey({ secret, onDone }: { secret: PartnerApiKeySecret; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret.api_key); setCopied(true); } catch { setCopied(false); }
  };
  return (
    <div className="card" style={{ background: '#fef9c3', border: '1px solid #fde68a', marginBottom: 16 }}>
      <strong>New key for {secret.name}</strong>
      <p style={{ fontSize: 13, margin: '6px 0' }}>
        Copy it now and share it with the partner privately. You won't be able to see it again.
      </p>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <code style={{ flex: 1, padding: '8px 10px', background: '#fff', borderRadius: 8, wordBreak: 'break-all' }}>{secret.api_key}</code>
        <button className="btn secondary sm" style={{ flex: '0 0 auto' }} onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
        <button className="btn sm" style={{ flex: '0 0 auto' }} onClick={onDone}>Done</button>
      </div>
    </div>
  );
}
