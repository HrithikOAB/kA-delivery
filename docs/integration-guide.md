# Digi Mess — Partner Integration Guide

This guide is for the **external ordering platform**. Orders are created and
owned by your platform; this backend only handles delivery. You register an
order id with us, ops assign a delivery partner, and you poll for live tracking.

- **Base URL:** `${API_BASE_URL}` (e.g. `http://localhost:8000`)
- **API prefix:** `/api/v1/partner`
- **Interactive docs:** `GET /docs` (Swagger UI) and `GET /openapi.json`
- **Auth:** shared secret in the `X-API-Key` header. See [Authentication](#authentication).
- **Errors:** `{"detail": "<message>"}` (a list of field errors for `422`).

---

## Authentication

Calls go both ways, and each direction has its own key.

| Direction | Who issues the key | Where it lives | How it is sent |
|---|---|---|---|
| You → us (`/api/v1/partner/*`) | We issue it to you | Admin console → **Settings → Partner API keys** (or the static `INTEGRATION_API_KEY`) | `X-API-Key: <key>` on every request |
| Us → you (`getRiderOrder`) | You issue it to us | Our `EXTERNAL_ORDER_API_KEY` | In the header you specify (`EXTERNAL_ORDER_API_KEY_HEADER`, default `x-api-key`) |

**You → us.** A super admin generates a key for you in the admin console
(**Settings → Partner API keys → Generate key**). Keys look like
`kd_live_…`; the full key is shown once, and we store only a hash of it. We
share it with you over a private channel. A super admin can **rotate** your key
(the old one stops working immediately) or **revoke** it, and can see when it
was last used. A missing, wrong, rotated-out or revoked key returns `401`; if
no key is configured at all the API returns `503`, so it is never open by
default.

**Us → you.** Give us a key for `getRiderOrder` and tell us the header name. For
a bearer token, we send `Authorization: Bearer <token>`. If your API rejects it
(`401`/`403`), ops see "External order API rejected our credentials".

> **Important:** `getRiderOrder` currently answers without any authentication and
> returns customer names, phone numbers and addresses to anyone who guesses an
> order id. Please enable auth on it and send us the key.

**Both directions:**
- Use HTTPS only; never send keys over plain HTTP.
- Never share keys in chat, email bodies or tickets in plain text.
- Rotate immediately if a key may have leaked: we rotate yours from the admin
  console (no restart needed); for yours, send us the new one and we update
  `EXTERNAL_ORDER_API_KEY` and restart.

---

## How it fits together

1. You call `POST /api/v1/partner/orders` with your order id. We store only the
   id and timestamps.
2. Ops open the order in the admin console. Order content (mess, customer,
   items, totals) is read **live** from your `getRiderOrder` API
   (`EXTERNAL_ORDER_API_URL`), so it is always current.
3. When ops assign a delivery partner, we read your API once more and cache the
   pickup, drop-off and contact details on our side so the rider app keeps
   working even if your API is briefly unavailable. Orders your API reports as
   `REJECTED` or `CANCELLED` cannot be assigned.
4. You call `POST /api/v1/partner/tracking` for status, partner details and the
   partner's live location.

Order ids may be sent as `"ORD-10001"` or `10001`; both refer to the same order
and responses always use the `ORD-<n>` form.

---

## 1. Register an order

```
POST /api/v1/partner/orders
X-API-Key: <key>
{ "order_id": "ORD-10001" }        // or { "orderId": 10001 }
```

`201` when created, `200` when the id was already registered (idempotent — safe
to retry):

```json
{
  "order_id": "ORD-10001",
  "internal_id": 42,
  "status": "placed",
  "created_at": "2026-10-11T12:08:25.510435",
  "already_existed": false
}
```

---

## 2. Track an order

```
POST /api/v1/partner/tracking
X-API-Key: <key>
{ "order_id": "ORD-10001" }        // or { "orderId": 10001 }
```

`404` if the id was never registered. Otherwise:

```json
{
  "order_id": "ORD-10001",
  "status": "out_for_delivery",
  "delivery_status": "picked_up",
  "updated_at": "2026-10-11T12:30:02.104Z",
  "delivery_partner": {
    "name": "Ravi Kumar",
    "phone": "+919000000002",
    "vehicle_type": "bike",
    "vehicle_number": "MH12AB1234",
    "rating": 4.8
  },
  "location": {
    "lat": 19.8912,
    "lng": 75.2731,
    "heading": 90,
    "speed": 4.1,
    "updated_at": "2026-10-11T12:30:00Z",
    "is_stale": false,
    "age_seconds": 2.1
  },
  "eta_minutes": 8,
  "distance_km": 1.9
}
```

- `delivery_partner` is `null` until a partner accepts the delivery.
- `location` is `null` until the partner's app has reported a position.
  `is_stale` / `age_seconds` tell you how fresh it is.
- `eta_minutes` / `distance_km` are `null` when your API has no customer
  coordinates for the order.
- Poll every 5–10 seconds while the order is active.

### Status values

`status` (order lifecycle):

```
placed → accepted → preparing → ready → assigned → picked_up → out_for_delivery → delivered
                                                                              ↘ cancelled
```

`delivery_status` (partner's progress): `pending`, `offered`, `accepted`,
`en_route_to_mess`, `picked_up`, `delivering`, `delivered`, `cancelled`, or
`null` before dispatch.

---

## 3. What we read from your API

`POST <EXTERNAL_ORDER_API_URL>` with `{ "order_id": "ORD-10001" }`. We use
`customer_details` (name, contact, address, location, instruction),
`mess_details` (name, contact, address, location — **location is required to
dispatch**), and `order_details` (items, totals in rupees, payment, and
`order_status`). A `404` / `success: false` response is shown to ops as
"order not found".
