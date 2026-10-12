# Environment Setup

## Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`. All values have safe local
defaults in `app/config.py`; override for anything non-local.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` / `DATABASE_USER` / `DATABASE_PASSWORD` | — | PostgreSQL connection (preferred). |
| `DATABASE_URL` | — | Optional full SQLAlchemy URL instead of component vars. |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | `admin@kadelivery.app` / — | First super-admin created when the DB has no users. |
| `AUTO_SEED_ADMIN_ON_STARTUP` | `true` | Bootstrap admin on empty DB at API startup. |
| `JWT_SECRET` | `dev-secret-change-me` | JWT signing key. **Set a long random value in prod.** |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Access-token lifetime. |
| `API_BASE_URL` / `WS_BASE_URL` | localhost | Informational (docs/clients). |
| `MAP_PROVIDER` | `none` | Backend keeps no map key; present for infra validation. |
| `LOCATION_UPDATE_INTERVAL_SECONDS` | `5` | Rider location cadence hint (surfaced to clients). |
| `LOCATION_DISTANCE_THRESHOLD_METERS` | `30` | Distance filter hint. |
| `LOCATION_STALE_SECONDS` | `30` | Age after which a rider fix is "stale". |
| `LOCATION_MAX_JUMP_METERS` | `2000` | Reject implausible position jumps. |
| `LOCATION_MAX_SPEED_MPS` | `55` | Reject fixes implying impossible speed. |
| `TRACKING_RETENTION_HOURS` | `24` | Location retention window. |
| `MAX_LOCATION_HISTORY` | `500` | Max stored fixes per rider (pruned). |
| `OTP_LENGTH` | `4` | Delivery OTP length. |
| `OTP_EXPIRY_MINUTES` | `30` | Delivery OTP validity. |
| `LOGIN_OTP_LENGTH` | `6` | Customer phone login OTP length. |
| `LOGIN_OTP_EXPIRY_MINUTES` | `5` | Customer login OTP validity. |
| `DISPATCH_OFFER_TIMEOUT_SECONDS` | `30` | Offer expiry before re-offering. |
| `DISPATCH_MAX_BATCH_SIZE` | `4` | Max orders per delivery batch. |
| `DISPATCH_MAX_MESS_RADIUS_KM` | `8` | Rider eligibility radius from mess. |
| `WS_RECONNECT_BASE_MS` / `WS_RECONNECT_MAX_MS` | `1000` / `15000` | Reconnect hints for clients. |
| `NOTIFICATION_PROVIDER` | `dev` | `dev` (in-memory/log) or `expo` (real push, needs wiring). |
| `EXPO_ACCESS_TOKEN` | _(empty)_ | For a real Expo push provider. |
| `PAYMENT_PROVIDER` | `cod` | `cod` (pay on delivery) or `mock` (instant paid). |
| `INTEGRATION_API_KEY` | _(empty)_ | Optional static key partners may send as `X-API-Key` to `/api/v1/partner/*`. Prefer keys issued from the admin console (**Settings → Partner API keys**). With neither configured the partner API returns 503. |
| `EXTERNAL_ORDER_API_URL` | getRiderOrder Prod URL | External API that returns order content (mess, customer, items, totals). |
| `EXTERNAL_ORDER_API_TIMEOUT_SECONDS` | `8` | Timeout for each external order API call. |
| `EXTERNAL_ORDER_API_KEY` | _(empty)_ | Credential the external platform issues to us for getRiderOrder. Sent only when set. |
| `EXTERNAL_ORDER_API_KEY_HEADER` | `x-api-key` | Header carrying that credential. For a bearer token use `Authorization` with the value `Bearer <token>`. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins. |

## Mobile (`mobile/.env`)

Copy `mobile/.env.example` to `mobile/.env`. Only `EXPO_PUBLIC_*` values are
readable by the app — **never put backend secrets here**.

| Variable | Default | Purpose |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` | Backend REST base. Use your LAN IP on devices. |
| `EXPO_PUBLIC_WS_URL` | `ws://localhost:8000` | Backend WebSocket base. |
| `EXPO_PUBLIC_MAP_PROVIDER` | `none` | `none` = dev fallback; `google`/`apple` = native map. |
| `EXPO_PUBLIC_MAP_API_KEY` | _(empty)_ | Client map key (safe to ship; restrict by app id). |
| `EXPO_PUBLIC_LOCATION_INTERVAL_MS` | `5000` | Rider location cadence. |
| `EXPO_PUBLIC_LOCATION_DISTANCE_M` | `30` | Rider distance filter. |

## Run commands

```bash
# Backend
cd backend
source .venv/bin/activate
alembic upgrade head            # apply migrations
python -m app.seed              # (re)seed demo data — idempotent
uvicorn app.main:app --reload   # serve
pytest                          # run tests

# Mobile
cd mobile
npm install
npx expo start                  # then press i / a, or scan the QR in Expo Go
npx tsc --noEmit                # typecheck
```

## Schema is owned by Alembic

The server does **not** auto-create tables — the schema is managed solely by
Alembic migrations. Always run migrations **before** starting the server or
seeding:

```bash
alembic upgrade head     # 1. create/upgrade schema
python -m app.seed       # 2. insert demo data
uvicorn app.main:app --reload   # 3. serve
```

**Troubleshooting — `table ... already exists`:** this means a database file
was created outside Alembic (an older build) and now conflicts with the
migration. Delete the local DB and re-run migrations:

```bash
rm -f digimess.db
alembic upgrade head
python -m app.seed
```

## SQLite → PostgreSQL migration

The code is DB-agnostic (enum columns are non-native VARCHAR, timestamps are
naive UTC). To move to PostgreSQL:

1. Provision Postgres and set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`.
2. `pip install "psycopg[binary]"`.
3. `alembic upgrade head` against the new database.
4. (Optional) migrate data with your preferred ETL; there is no SQLite-specific
   SQL in the models or migrations (`render_as_batch` is only needed for SQLite
   ALTERs and is harmless elsewhere).

## Location permissions & background limits

The rider app requests **foreground** location permission and only broadcasts
while online **with an active delivery**. Continuous background tracking is out
of scope; OS background-execution limits mean location updates pause when the
app is backgrounded. The backend independently stops exposing a rider's location
once the order is terminal.

## Maps & builds

`react-native-maps` is **not available in Expo Go**. With `MAP_PROVIDER=none` the
app uses the labeled dev fallback and runs in Expo Go. To use real maps, set the
provider + key and create a development build (`npx expo run:ios` /
`npx expo run:android` or EAS).
