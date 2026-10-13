# Digi Mess — End-to-End Food Delivery App

A complete food-ordering and delivery **mobile** application: a FastAPI + SQLite
backend and a React Native (Expo + TypeScript) app with **three roles**
(customer, delivery partner, and a mess/kitchen role), separate logins,
role-based navigation, and Zomato-style live delivery tracking over WebSockets
with a REST fallback.

```
digi-mess/
├── backend/   FastAPI + SQLAlchemy + Alembic (SQLite), JWT auth, WebSocket tracking
├── mobile/    Expo + React Native + TypeScript (expo-router) — delivery-partner app
├── admin/     Vite + React + TypeScript admin dashboard (verification, ops map,
│              orders/issues, delivery assignment)
└── docs/      Environment setup, implementation status, partner integration guide
```

Orders are owned by an **external ordering platform**. The platform registers an
order id through the partner API (`POST /api/v1/partner/orders`); the admin
console reads the order's content live from the platform's `getRiderOrder` API,
ops assign a delivery partner, and the platform polls
`POST /api/v1/partner/tracking` for status and live location. See the
[partner integration guide](docs/integration-guide.md).

## Features

- **External partner API**: register an order id, poll status or tracking,
  cancel when needed. Authenticated with `X-API-Key`.
- **Delivery partner**: register (+ vehicle info) with approval gating,
  go online/offline, receive & accept/reject batched delivery offers, navigate,
  confirm pickup, **complete each stop with the customer's OTP**, and view
  earnings/payouts.
- **Live tracking**: rider location ingestion with validation (ownership,
  freshness, implausible-jump/speed rejection), order-scoped WebSocket push,
  REST snapshot fallback, reconnect with backoff, stale-location indicators, and
  **access revocation once delivered/cancelled**.

## Order lifecycle

`placed → accepted → preparing → ready → assigned → picked_up → out_for_delivery → delivered`
(+ `cancelled`). All transitions are **server-authoritative** and audited; the
client never dictates status. Dispatch batches ready orders per mess and offers
them to eligible online riders, re-offering on reject/expiry (see
`mermaid-diagram.png`).

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # adjust secrets for anything non-local
uvicorn app.main:app --reload      # http://localhost:8000  (docs at /docs)
# On first start the API auto-migrates and seeds an empty DB.
# Manual alternative: alembic upgrade head && python -m app.seed
```

Run the tests:

```bash
cd backend && pytest
```

### 2. Mobile

```bash
cd mobile
npm install
cp .env.example .env               # set EXPO_PUBLIC_API_URL to your machine's LAN IP for devices
npx expo start
```

> On a physical device, `localhost` is the phone — set
> `EXPO_PUBLIC_API_URL`/`EXPO_PUBLIC_WS_URL` to your computer's LAN IP
> (e.g. `http://192.168.1.20:8000`).

### 3. Admin dashboard (web)

```bash
cd admin
npm install
cp .env.example .env               # VITE_API_URL defaults to http://localhost:8000
npm run dev                        # http://localhost:5173
```

The admin dashboard (React + TypeScript + Vite, maps via Leaflet + OpenStreetMap —
no map key required) provides partner **verification**, **partner management**,
a **live operations map**, and **orders & issues** with delivery assignment. It talks to the same backend; ensure the backend
`CORS_ORIGINS` permits `http://localhost:5173` (the default `*` already does).

### Demo accounts

Customers sign in by **phone + OTP** — use `+919000000001` (the seeded customer)
or any number to create a new account. In dev the code is returned in the API
response and shown in the app, so no SMS gateway is needed.

Admins, riders and mess owners sign in with **email + password** (`password123`):

| Role     | Email                    | Notes                                        |
|----------|--------------------------|----------------------------------------------|
| Admin    | `admin@kadelivery.app`     | Super admin (all permissions)                |
| Admin    | `verifier@digimess.app`  | Partner-verification tier                    |
| Admin    | `ops@digimess.app`       | Operations tier (assignment, live map)       |
| Rider    | `rider@digimess.app`     | Approved; can go online                      |
| Rider    | `applicant@digimess.app` | Application **under review** (approve in UI) |
| Mess     | `mess@digimess.app`      | Owns "Digi Mess Kitchen"                     |
| Combo    | `combo@digimess.app`     | customer + rider (role switch demo)          |

> Brand palette: **indigo `#5B3DF5`**, **mint `#19C6A5`**, **amber `#FFC857`**.
> There is **no public admin signup** — admins are provisioned by the seed only.

## End-to-end demo flow (admin + delivery partner)

This is the primary golden path for the delivery-partner platform:

1. **Admin** (`admin@kadelivery.app`) signs in to the dashboard → **Partner
   verification** → open `applicant@digimess.app` → review documents → **Approve**.
2. On mobile, the approved **partner** signs in and taps **ONLINE**.
   (New applicants upload documents under **Manage documents & verification**.)
3. **Admin** → **Settings** → **Partner API keys** → **Generate key**, then
   register an order id with it:
   `curl -X POST localhost:8000/api/v1/partner/orders -H 'X-API-Key: <key>' -H 'Content-Type: application/json' -d '{"order_id":"ORD-10001"}'`.
   It appears under **Orders**; opening it loads the details from the external
   order API.
4. **Admin** → open the order → **KA Delivery partner** → **Send offer** to the
   online partner. The pickup/drop-off details are cached at this point.
5. **Partner** receives the offer → accepts → **Mark arrival** → **Confirm pickup**;
   the device location broadcast begins.
6. **Admin** → **Live operations** map shows the moving marker with a
   last-updated time and a **stale** indicator if updates stop.
7. **Partner** enters the delivery **OTP** → **Complete delivery**. Meanwhile
   `POST /api/v1/partner/tracking` returns the partner's details and location.
8. **Admin** → **Orders & issues** shows the final status and full timeline;
   earnings update in the partner app.

> The **customer ordering app** is not part of this project — orders come from
> the external platform via [`docs/integration-guide.md`](docs/integration-guide.md).

## Maps

The tracking screen uses a **configurable map provider**. With no map key
(`EXPO_PUBLIC_MAP_PROVIDER=none`) it renders a clearly-labeled **dev fallback**
that plots the real mess/customer/rider markers on a schematic grid — so the app
runs in **Expo Go**. Set `EXPO_PUBLIC_MAP_PROVIDER=google` + a client key and
build a dev/prod client to enable native `react-native-maps`.

## Documentation

- [`docs/integration-guide.md`](docs/integration-guide.md) — contract for the
  **external ordering platform**: order registration and tracking.
- [`docs/environment-setup.md`](docs/environment-setup.md) — every environment
  variable, SQLite→PostgreSQL migration, run commands.
- [`docs/implementation-status.md`](docs/implementation-status.md) — what's done,
  architecture, WebSocket event format, and known limitations.

## Security notes

- Role-based access control in FastAPI; a customer cannot hit rider-only
  endpoints and a rider cannot touch another rider's assignment.
- WebSocket tracking is authenticated and **order-scoped** — one customer cannot
  subscribe to another's order.
- Backend secrets live only in the backend `.env`; the mobile app only ever sees
  `EXPO_PUBLIC_*` values.
