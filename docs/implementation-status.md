# Implementation Status

## Summary

End-to-end app is implemented: FastAPI backend (fully tested) + Expo/React
Native app (typechecked). All 7 planned phases are in place.

| Phase | Status |
|---|---|
| 1. Backend foundation (FastAPI, SQLite, migrations, auth) | ✅ Done + tests |
| 2. RN foundation + role-based logins | ✅ Done |
| 3. Customer ordering (discovery, cart, server checkout, orders) | ✅ Done |
| 4. Mess workflow (accept/prepare/ready + dispatch) | ✅ Done |
| 5. Rider workflow (online, offers, pickup, OTP completion, earnings) | ✅ Done |
| 6. Live tracking (WS push + REST fallback, validation, revocation) | ✅ Done |
| 7. Notifications, error handling, tests, docs, polish | ✅ Done (push stubbed) |

## Backend architecture

- **Models** (`app/models`): `User` (+`RiderProfile`, `Address`), `Mess`,
  `MenuItem`, `Order`(+`OrderItem`), `DeliveryBatch`, `Delivery`,
  `DeliveryOffer`, `RiderLocation`, `AuditEvent`. Enum columns are VARCHAR-backed
  (`sa_enum`) for Postgres portability; timestamps are naive UTC.
- **Services** (`app/services`): `auth_service`, `state_machine` (allowed
  transitions + audit), `dispatch_service` (batching + offer loop),
  `location_service` (validation/freshness/pruning), `tracking_service`
  (snapshot + authorization), `ws_manager` (order pub/sub), `eta_service`
  (haversine + ETA), `earnings_service`, `external_order_client` (external
  getRiderOrder API), `order_hydration_service` (caches external order content at
  assignment), `partner_order_service` (partner registration + tracking),
  `notification_service` (dev/expo), `payment_service` (cod/mock).
- **API** (`app/api/v1`): `auth`, `rider`, `deliveries`, `admin`, `partner`,
  `maps`, `tracking_ws`, plus `/config` and `/health`.

## Authentication & roles

- **Customers sign in by phone + OTP**: `POST /auth/customer/otp/request` issues a
  code (SMS in prod; returned as `dev_code` in dev), `POST /auth/customer/otp/verify`
  logs in and creates the customer on first use. Email/password customer login is
  retained for tooling/tests.
- Separate login endpoints per role: `/auth/customer/login`, `/auth/rider/login`,
  `/auth/mess/login`. Riders register but are `pending`
  until approved (they cannot act as a rider until then). Privileged roles are
  never self-granted at signup.
- JWT carries `sub` + active `role`; `require_role`/`require_approved_rider`
  guard endpoints. Role switch (`/auth/role/switch`) is limited to roles the
  account already holds.

## Order lifecycle & dispatch

`placed → accepted → preparing → ready → assigned → picked_up →
out_for_delivery → delivered` (+ `cancelled`). Marking an order **ready** batches
it (per mess, up to `DISPATCH_MAX_BATCH_SIZE`) and offers the batch to the
nearest eligible online rider; reject/expiry re-offers to the next. Pickup moves
the whole batch out for delivery; each stop completes independently with the
customer's OTP; when all stops are delivered the batch completes and payout is
reconciled.

## Live tracking

### REST
- `POST /api/v1/partner/tracking` (`X-API-Key`) — external-partner tracking by
  order id: status, delivery partner details, live location with
  `is_stale`/`age_seconds`, and ETA/distance.
- `GET /api/v1/admin/orders/{order_id}/tracking` — admin order-scoped snapshot
  (markers, rider marker, ETA/distance, progress timeline).

### WebSocket
- `WS /api/v1/orders/{order_id}/tracking/ws?token=<JWT>` — authenticated,
  order-scoped. Close codes: `4401` unauthorized, `4403` forbidden (not your
  order), `4404` order not found.
- **Message format**: `{"type": "snapshot", "data": <TrackingSnapshot>}`.
- Server pushes a snapshot on connect, on each rider location update, and on a
  periodic timer (so status changes surface); it sends a final snapshot and
  closes once the order is terminal (**tracking access revoked**).

### Location ingestion (`POST /api/v1/rider/location`)
- Allowed only while the rider is online **and** has an active delivery.
- Validates coordinate ranges (schema), future/too-old timestamps, and
  implausible jump/speed vs. the previous fix. Server receipt time is stored
  separately from the device timestamp; a fresh position is never presented as
  live once stale.

### Client reliability
- The app seeds from REST, opens the socket, reconnects with exponential backoff
  (capped), and **polls REST while the socket is down** so the screen never goes
  blank. It re-fetches the snapshot on every (re)connect.

## UI

Clean light theme: white surfaces, **orange** primary (`#F97316`), **blue**
accents (`#2563EB`), soft card shadows, rounded inputs. Tokens live in
`src/theme.ts` and the shared kit in `src/ui/components.tsx`, so the look is
consistent across all screens.

## Tests (`backend/tests`) — 22 passing

Auth & roles; wrong-password; role guards; role switch; unapproved-rider gating;
server-computed checkout; invalid/stale/implausible location rejection;
location-requires-active-delivery; tracking snapshot shape; tracking
authorization (other customer blocked); WS authorized snapshot; WS rejects other
customer / missing token; rider-cannot-complete-another's-delivery; OTP
required/incorrect; **end-to-end order→delivery**; tracking revoked after
completion; REST reconnection recovery.

## Known limitations / stubs

- **Push notifications**: `notification_service` records to memory/log in `dev`;
  the Expo provider is a wired interface but intentionally not sending (no
  silent pretend-delivery). Real push needs `NOTIFICATION_PROVIDER=expo` +
  device-token registration.
- **Payments**: cash-on-delivery / mock behind `payment_service`; no real
  gateway.
- **Maps**: dev fallback unless a provider key is set and a dev/prod build is
  used (not Expo Go).
- **Background location**: foreground-only by design (see environment-setup).
- **Customer ordering app**: intentionally not built; its backend contract is in
  `docs/integration-guide.md`.

## Delivery-partner platform (admin dashboard + partner API)

Added on top of the base app:

- **Admin identity & RBAC**: an `admin` role with four backend-enforced tiers
  (`super_admin`, `partner_verification`, `operations`, `support`) via
  `require_admin_permission`. Admin login at `POST /api/v1/auth/admin/login`;
  **no public admin signup**. Sensitive admin actions are written to the
  append-only `AuditEvent` log (actor, action, target, reason).
- **Partner verification**: 6-state lifecycle
  (`draft → submitted → under_review → approved | rejected | needs_correction`)
  with document upload (`POST /rider/documents`, stored under `UPLOAD_DIR`),
  admin review/approve/reject/request-correction, and resubmission. Only
  `approved` partners pass `require_approved_rider` (backend-enforced gate).
- **External orders**: the external platform registers an order id via
  `POST /api/v1/partner/orders` (`X-API-Key`). The admin order page reads mess,
  customer, items and totals live from the external `getRiderOrder` API
  (`external_order_client`); on assignment `order_hydration_service` caches that
  content on the order so dispatch and the rider app work unchanged.
  `POST /api/v1/partner/tracking` returns status, partner details and live
  location (built on `tracking_service.build_snapshot`). The old full-payload
  ingestion endpoint, the test-order tool, and the customer/mess-owner order APIs
  were removed.
- **Dashboard data & ops map**: live overview metrics, partner search + detail +
  suspend/reactivate, orders/issues with delivery timeline + internal notes, and
  a Leaflet/OSM operations map that **reuses** `tracking_service.build_snapshot`
  (`GET /admin/deliveries/active`, `GET /admin/orders/{id}/tracking`) — no second
  tracking system. Admin tracking is order-scoped via `admin_can_view`.
- **Admin web app** (`admin/`): Vite + React + TS, JWT auth, role-gated nav, and
  loading / empty / error / stale states throughout.
- **Tests**: `tests/test_admin.py` covers admin auth + permission
  tiers, verification transitions + audit, document upload/fetch, admin tracking
  access, and suspend/reactivate; `tests/test_partner_orders.py` covers order
  registration, live external detail, assignment caching, and partner tracking.

## Manual verification

Backend is verified by the automated suite and a live-server smoke test. The
mobile app is typechecked (`npx tsc --noEmit`); run it on a device/emulator with
`npx expo start` and follow the end-to-end flow in the root `README.md`.
