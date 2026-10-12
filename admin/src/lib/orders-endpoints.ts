/**
 * Static reference of the admin API endpoints the Orders page uses.
 * Shown in the developer inspector's "Reference" tab. Keep in sync with
 * `api/client.ts` and `backend/app/api/v1/admin.py`.
 */

export interface EndpointDoc {
  method: string;
  path: string;
  description: string;
  requestExample?: unknown;
}

export const ORDERS_ENDPOINTS: EndpointDoc[] = [
  {
    method: 'GET',
    path: '/admin/orders?q&status&limit',
    description: 'List orders stored locally (search by order id or external ORD- id, filter by status).',
  },
  {
    method: 'GET',
    path: '/admin/orders/{order_id}',
    description: 'Order detail. Mess, customer, items and totals are fetched live from the external order API; assignment, timeline and issues come from our DB.',
  },
  {
    method: 'GET',
    path: '/admin/orders/{order_id}/candidate-riders',
    description: 'Approved online partners ranked nearest-first to the mess, with availability.',
  },
  {
    method: 'POST',
    path: '/admin/orders/{order_id}/assign',
    description: 'Assign delivery to a KA partner (offer) or an external platform.',
    requestExample: { mode: 'internal', rider_id: 12 },
  },
  {
    method: 'POST',
    path: '/admin/orders/{order_id}/assign',
    description: 'External-platform variant of the assign call.',
    requestExample: { mode: 'external', provider: 'zomato', reference: 'ZOM-123', note: 'rush' },
  },
  {
    method: 'POST',
    path: '/admin/orders/{order_id}/external-status',
    description: 'Advance the manually-tracked status of an externally-fulfilled order.',
    requestExample: { status: 'delivered' },
  },
  {
    method: 'POST',
    path: '/admin/issues/{issue_id}/note',
    description: 'Add an admin resolution note to a reported issue.',
    requestExample: { note: 'Called customer, reattempting delivery.' },
  },
  {
    method: 'POST',
    path: '/admin/issues/{issue_id}/resolve',
    description: 'Mark a reported issue resolved.',
  },
];
