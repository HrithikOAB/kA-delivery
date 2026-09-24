# Plan: Production Readiness — DigiMess (delivery + dispatch + live tracking)

**Complexity:** Large · **Mode:** whole-flow audit → prioritized fix plan
**Confirm before I start coding.**

## Summary
The backend API surface is **complete** — every `api.*` call in the rider app and admin maps to an implemented endpoint (auth, onboarding/verification, order→dispatch→offer→accept→pickup→delivery→OTP→completion, earnings/wallet/withdrawals, tracking, maps, plus customer/mess flows). Nothing is a "missing endpoint." What blocks production is: (1) the **live-location pipeline never gets data from the app** (insecure origin + permission + silent failure), (2) **deploy/config** (HTTP on a raw IP breaks Google Maps JS + geolocation; `ws://`; CORS; unrestricted committed API key), (3) a **security bypass** (default OTP `1212`) and prod-unsafe **auto-seed/migrate on startup**, and (4) the **dispatch offer race**. Maps rendering was largely fixed earlier this session.

## Audit method
Cross-checked backend routes (`backend/app/api/v1/*.py`) against client calls (`mobile/src/api/client.ts`, `admin/src/api/client.ts`) — surfaces match. Root causes below are grounded in code read this session; items marked ⚠️ need a quick confirm during implementation.

---

## P0 — Live tracking actually works end-to-end (the core complaint)

| # | Issue | Where | Fix |
|---|---|---|---|
| 1 | Rider web app on an **insecure origin** (`http://IP`) → browsers **block `navigator.geolocation`** entirely → zero location posts | runtime / deploy | Serve rider web + admin over **HTTPS** (see P0-deploy). `localhost` works; raw `http://IP` never will. |
| 2 | Broadcast **fails silently** — permission denied / geo error is swallowed, nothing shown | `mobile/src/lib/rider-location(.web).ts`, `RiderLiveLocation.tsx` | Surface status via existing `useRiderLocationStatus()`: render a badge ("Live • tracking" / "Permission denied" / "Location needs HTTPS") on rider Home + offer screens; `console.warn` on post failure. |
| 3 | Permission not requested assertively when going online | `useRiderLocationBroadcast`, `useRiderPosition` | Request foreground permission on online-toggle; block "go online" with a clear prompt if denied. |
| 4 | Background tracking needs the **custom dev build** (not Expo Go) | `background-location.ts`, `app.config.js` | Build & distribute the dev/prod client (Maps SDK + background location already wired). |
| 5 | Staleness dropped markers after 30s | `backend/app/config.py:50` | ✅ done → 90s (needs backend redeploy). |
| 6 | No way to demo tracking without phones | — | ✅ added `backend/simulate_partner_tracking.py`. |

**Verify:** rider grants location + online → DevTools Network shows `POST /api/v1/rider/location` 200 every ~5s → admin Live Tracking plots the partner within 5s, marker persists 90s.

## P0 — Deploy / config correctness (unblocks maps + tracking together)
| # | Issue | Where | Fix |
|---|---|---|---|
| 7 | Whole stack on **`http://13.201.237.11`** → breaks Google Maps JS (referrer can't authorize a bare IP), geolocation (insecure origin), and secure cookies | infra | Put API + admin + rider-web behind a **domain with TLS** (reverse proxy). This single change unblocks #1, Google JS auth, and wss. |
| 8 | `EXPO_PUBLIC_WS_URL=ws://delivery-api.khanaanywhere.com` (insecure ws vs https host) | `mobile/.env` | → `wss://…`. |
| 9 | `admin/.env VITE_API_URL=http://localhost:8001` ≠ backend the rider posts to | `admin/.env` (build-time) | Point admin build at the real backend (`https://delivery-api.khanaanywhere.com`). |
| 10 | CORS `allow_origins="*"` + `allow_credentials=True` (invalid combo; insecure) | `backend/app/main.py:48-54`, `config.py:85` | Set `cors_origins` to explicit admin/web origins; keep credentials only if needed. |
| 11 | Google APIs **not enabled** (Static Maps + Routes returned 403 "not activated" this session) | GCP | Enable Maps JavaScript, Maps SDK Android/iOS, Static Maps, Routes, Places; set key restrictions to the new domain(s). |
| 12 | Google Maps API key **committed** in `mobile/.env` and `admin/.env` | repo | Rotate key; restrict by API + referrer/app; keep only public client keys client-side. |

## P0 — Security / prod-safety
| # | Issue | Where | Fix |
|---|---|---|---|
| 13 | **Default OTP `1212` bypasses login/verification** and "never expires" | `backend/app/config.py` (`default_otp`), `auth_service.py:230,297`, `otp_service.py` | Disable in production (empty/env-gated so the bypass is dev-only). CRITICAL — anyone can log in as any phone today. |
| 14 | ⚠️ **Auto-migrate + auto-seed on startup** seeds test users/admin/messes | `backend/app/main.py`, `seed.py` (commit "Implement automatic database migration and seeding on API startup") | Gate seeding behind an env flag; never seed demo data / default admin in prod; run migrations as a deliberate step. |
| 15 | ⚠️ Committed `.env` files (backend/admin/mobile) with secrets | repo | Move real secrets to server env / secret manager; keep only `.env.example`. |

## P1 — Dispatch offer race ("Offer is no longer available") — exclusive policy (you chose this)
| # | Issue | Where | Fix |
|---|---|---|---|
| 16 | Accept 409s because the batch was assigned to another rider while the offer was open | `dispatch_service.py:266-274, 559-564` | (a) Make `accept_offer` **idempotent** when the batch is already assigned to the *same* rider. (b) **Block admin manual-assign / auto-assign** from taking a batch that is currently `offered` to a *different* rider unless explicitly forced. (c) Return a clear "assigned to another partner" message otherwise. |

## P1 — Maps (mostly fixed this session; finish)
- ✅ Admin Google-only (`MapView.tsx`), road route via OSRM (`admin/src/lib/directions.ts`), native Google markers, `expo-location` perms.
- Finish: native interactive Google needs Maps SDK enabled + dev build (P0 #4/#11).

## P2 — Hardening / QA
- Replace remaining silent `except`/swallowed errors in the location + dispatch paths with logging + user-visible states. ⚠️ audit `location_service`, broadcasters, WS.
- Add end-to-end tests for the delivery + tracking flow (many `test_*` exist — extend to cover dispatch race + location ingest edge cases: `implausible_jump/speed/timestamp_too_old`).
- Confirm the **customer** ordering + tracking apps (backend `/customer/*`, `/checkout`, `/orders/{id}/tracking`, `tracking_ws.py`) have a deployed front-end, or descope for v1.
- Retention/scale: `RiderLocation` history pruning (`max_location_history`, `tracking_retention_hours`) is fine; confirm DB indexes on `RiderLocation(rider_id, server_timestamp)`.

## Validation (per phase)
```bash
# backend
cd backend && python -m pytest -q          # extend tests for dispatch + location
cd backend && python simulate_partner_tracking.py --center 19.0971,72.8935   # live map demo
# admin / mobile
cd admin && npx tsc --noEmit
cd mobile && npx tsc --noEmit
# end-to-end: rider (https) online + permission → POST /rider/location 200 → admin marker moves
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Without HTTPS/domain, geolocation + Google JS can never work | Certain | P0 #7 is the keystone — do it first |
| Disabling default OTP locks out testers | Med | Env-gate: bypass only when `ENV=dev` |
| Turning off auto-seed empties a prod DB expecting seed data | Med | Verify prod DB has real data before disabling |
| Exclusive-offer change alters dispatch behavior | Med | Cover with tests before deploy |

## Acceptance
- [ ] Rider (over HTTPS) online + permission → live position visible & moving on admin within 5s, persists 90s
- [ ] Google Maps renders on admin + app with an authorized key; no OSM fallback needed
- [ ] Offer accept never spuriously 409s for the offered rider
- [ ] Default-OTP bypass disabled in prod; no secrets in repo; CORS locked to known origins
- [ ] `tsc` clean (admin+mobile); backend tests green

## Suggested execution order
1. **P0 deploy/config** (#7 domain+TLS, #8 wss, #9 admin URL, #10 CORS, #11 GCP APIs, #12 key) — keystone.
2. **P0 security** (#13 OTP, #14 seeding, #15 secrets).
3. **P0 live-tracking app** (#2 surface status, #3 permission, #1 verified via HTTPS, #4 dev build).
4. **P1 dispatch race** (#16).
5. **P2 hardening/tests.**
