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
│              orders/issues, and the admin-only Create Test Delivery tool)
└── docs/      Environment setup, implementation status, customer-app integration guide
```

The **admin dashboard** and **admin-only test-order tool** are first-class parts
of this project. The **customer ordering app is intentionally not built** — its
backend contract is documented for a separate team (see the integration guide).

## Features

- **Customer**: **phone + OTP** sign-in, saved addresses, mess discovery (distance-sorted),
  menu browsing, cart, **server-computed checkout**, order placement, order
  history (offline-cached), and a polished **live tracking** screen.
- **Delivery partner**: register (+ vehicle info) with approval gating,
  go online/offline, receive & accept/reject batched delivery offers, navigate,
  confirm pickup, **complete each stop with the customer's OTP**, and view
  earnings/payouts.
- **Mess/kitchen**: accept → prepare → mark ready, which triggers dispatch.
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
a **live operations map**, **orders & issues**, and the admin-only
**Create Test Delivery** tool. It talks to the same backend; ensure the backend
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
| Admin    | `ops@digimess.app`       | Operations tier (test orders, live map)      |
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
3. **Admin** → **Create Test Delivery** → pick pickup + drop-off on the map (or
   enter coordinates) → **Review & create**. The order is marked **TEST** and
   appears as an unassigned delivery.
4. **Admin** advances it (Accept → Prepare → Ready); the real dispatch engine
   assigns/offers it to the online partner.
5. **Partner** receives the offer → accepts → **Mark arrival** → **Confirm pickup**;
   the device location broadcast begins.
6. **Admin** → **Live operations** map shows the moving marker with a
   last-updated time and a **stale** indicator if updates stop.
7. **Partner** enters the delivery **OTP** (shown on the test order) → **Complete
   delivery**. Test orders never fire real payments or customer notifications.
8. **Admin** → **Orders & issues** shows the final status and full timeline;
   earnings update in the partner app.

> The **customer ordering app** is intentionally **not** built here — the backend
> exposes the contract for it in [`docs/integration-guide.md`](docs/integration-guide.md).

## Maps

The tracking screen uses a **configurable map provider**. With no map key
(`EXPO_PUBLIC_MAP_PROVIDER=none`) it renders a clearly-labeled **dev fallback**
that plots the real mess/customer/rider markers on a schematic grid — so the app
runs in **Expo Go**. Set `EXPO_PUBLIC_MAP_PROVIDER=google` + a client key and
build a dev/prod client to enable native `react-native-maps`.

## Documentation

- [`docs/integration-guide.md`](docs/integration-guide.md) — contract for the
  separate **customer-app team**: order creation, status, tracking snapshot + WS.
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
