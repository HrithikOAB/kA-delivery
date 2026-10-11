import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import { Page } from '@/components/Layout';
import { AsyncView } from '@/ui/kit';
import { ApiInspector } from '@/components/ApiInspector';
import { money } from '@/theme';

const ORDER_STATUSES = ['placed', 'accepted', 'preparing', 'ready', 'assigned', 'picked_up', 'out_for_delivery', 'delivered', 'cancelled'];

export function Orders() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [testFilter, setTestFilter] = useState('');
  const { data, loading, error, stale, reload } = useAsync(
    () => api.orders({ q: q || undefined, status: status || undefined, is_test: testFilter === '' ? undefined : testFilter === 'true' }),
    [q, status, testFilter],
    20000
  );

  return (
    <Page title="Orders">
      <div className="filters">
        <input placeholder="Order # or partner" value={q} onChange={(e) => setQ(e.target.value)} style={{ padding: '9px 12px', borderRadius: 10, border: '1px solid #e5e7eb' }} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {ORDER_STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={testFilter} onChange={(e) => setTestFilter(e.target.value)}>
          <option value="">Real + test</option>
          <option value="false">Real only</option>
          <option value="true">Test only</option>
        </select>
      </div>
      <AsyncView data={data} loading={loading} error={error} onRetry={reload} stale={stale} isEmpty={(d) => d.items.length === 0} emptyTitle="No orders match">
        {(d) => (
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead><tr><th>Order</th><th>Status</th><th>Customer</th><th>Delivery</th><th>Total</th><th>Type</th></tr></thead>
              <tbody>
                {d.items.map((o) => (
                  <tr key={o.order_id} className="clickable" onClick={() => navigate(`/orders/${o.order_id}`)}>
                    <td>#{o.order_id}<div className="muted" style={{ fontSize: 12 }}>{o.mess_name}</div></td>
                    <td>{o.status}{o.delivery_status ? ` / ${o.delivery_status}` : ''}</td>
                    <td>{o.customer_name ?? '—'}</td>
                    <td>
                      {o.fulfillment_type === 'external'
                        ? <span className="badge" style={{ background: '#fef3c7', color: '#d97706' }}>{(o.external_provider ?? 'external').toUpperCase()}</span>
                        : (o.rider_name ?? <span className="muted">unassigned</span>)}
                    </td>
                    <td>{money(o.total_cents)}</td>
                    <td>{o.is_test ? <span className="badge test">TEST</span> : <span className="muted">Real</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>
      <ApiInspector />
    </Page>
  );
}
