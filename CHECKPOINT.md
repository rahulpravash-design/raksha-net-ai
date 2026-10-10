# CONTINUE FROM HERE

**Checkpoint date:** 2026-10-10
**Branch:** `claude/raksha-net-ai-development-5uyq42`
**Last commit:** see `git log -1` (Phase 16 security hardening, then its documentation)
**State:** Clean. Working tree empty, every check green, everything pushed.

> Read this file, then `docs/ROADMAP.md`, then `CLAUDE.md`. Do not redesign
> anything marked COMPLETE below — it is built, tested and verified.

---

## 1. Where the project stands

**Phases 0–14 are implemented, except Phases 8 and 9. Phase 16 is code-complete,
but its penetration test and risk acceptance have NOT happened.**

| Phase | State |
|---|---|
| 0 Foundation | ✅ complete |
| 1 Auth & identity | ✅ complete |
| 2 Citizen reporting | ✅ complete |
| 3 Incident management | ✅ complete |
| 4 GIS & location | ✅ complete |
| 5 Control centre | ✅ complete |
| 6 AI emergency analyzer | ✅ complete (rule-based baseline, deliberately) |
| 7 Priority engine hardening | ✅ complete |
| 8 Computer vision | ⬜ not started |
| 9 Voice & multilingual | ⬜ not started |
| 10 Resource coordination | ✅ complete |
| 11 Dispatch & responder app | ✅ complete |
| 12 Hospital coordination | ✅ complete |
| 13 Notifications | ⚠️ partial — in-app complete, SMS/email/push stubbed |
| 14 Analytics | ✅ complete |
| 15 Prediction | ⬜ deliberately skipped — no historical dataset exists |
| 16 Security hardening | ⚠️ **code-complete; pen test + authority acceptance NOT done** |
| 17 Performance & scale | ⬜ **next** |
| 18 Production readiness | ⬜ not started |

**Verification at checkpoint time** — all of this was run, not assumed:

- `./scripts/check.sh` — **19/19 steps green** (ruff, black, mypy, pytest, AI
  pytest, pip-audit, npm audit, then eslint + tsc + vitest + build for all three
  front ends). Read from its actual final line (`All checks passed.`).
- **407 backend tests**, **31 AI tests**, **90 frontend tests** (45 citizen, 40
  control centre, 5 responder). 528 total, all passing.
- Migrations `0001 → 0012`. Each new one (0009–0012) was applied, rolled back
  and re-applied; `0010` (which rewrites data) was proven on a planted
  plaintext row in both directions.
- **A live end-to-end run** in a real Chromium against the running API and the
  built front ends: a dispatcher and a citizen sign in through the UI (dashboard
  stats and the Leaflet map render), and the full MFA path — enrol, API login
  demands a code, UI reveals the code field, sign in with a code from an
  *independent* TOTP implementation, admin resets MFA — with zero CSP violations.
  These scripts lived in the scratchpad and are **not** in the repository (see
  §5, item 14).
- 267 tracked files, 12 migrations, 68 API operations.

---

## 2. Current working feature — finished, nothing half-done

Phase 16 (security hardening) was the last thing built. Everything is committed;
there is no partially-written code. Details and limits: `docs/SECURITY.md`.

- **Account lockout** — 5 failures → 15 min, doubling per further failure,
  capped at 24 h; only a successful login resets it. Audited. Admin unlock:
  `POST /users/{id}/unlock`.
- **TOTP MFA** — `/auth/mfa/{enroll,enable,disable}`; replay protection; wrong
  codes count toward lockout; secret encrypted at rest;
  `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL` blocks un-enrolled non-citizens (in the
  default current-user dependency, so new endpoints inherit it); admin
  `POST /users/{id}/reset-mfa` (also revokes sessions; not allowed on yourself).
  All three sign-in pages accept a code.
- **Encryption at rest** — `contact_phone` on incidents/resources/hospitals and
  `users.mfa_secret`, via `EncryptedString`; dedicated, rotatable
  `RAKSHA_ENCRYPTION_KEY`. Raw SQL bypasses the type (the hospital nearby query
  decrypts by hand) — remember this for any new raw query touching these columns.
- **Headers/CSP** — API (`default-src 'none'`) and all three Next.js apps.
- **Malware scanning** — `Scanner` interface; `NullScanner` records `UNSCANNED`;
  ClamAV `INSTREAM` client when `RAKSHA_CLAMAV_HOST` is set.
- **Audit gating** — pip-audit and `npm audit --omit=dev` in CI and `check.sh`.
  The first run found real advisories (PyJWT; Next.js incl. a critical), fixed:
  PyJWT 2.15.0, Next/eslint-config-next 16.3.8.
- Docs brought current: `API.md` (it still listed phases 10–14 as "planned"),
  `DATABASE.md`, `SECURITY.md`, `RUNBOOK.md`, `.env.example`.

Two lessons, in case the pattern recurs:

1. **`ruff S608` flags any f-string passed to `text()`**, even over static
   fragments. Don't suppress it; write static SQL (done in analytics, the
   encryption tests and migration 0010).
2. **A SQL alias that shares a column's name makes `GROUP BY` bind the raw
   column** (the Phase 14 hotspot bug). Group on the expression.

---

## 3. The exact next step

**Start Phase 17 — Performance & scalability.** From `docs/ROADMAP.md`: load
testing against the NFR targets, query tuning, caching, partitioning,
connection-pool tuning, read replicas.

Be honest about what an agent session can show. A load test run against a
single sandbox machine proves nothing about production capacity; it can find
algorithmic problems (N+1 queries, missing indexes, slow endpoints) and give a
reproducible number. Read the NFR targets in `docs/PRD.md` first, then, in order:

1. **A runnable load-test script** (`scripts/loadtest.*`, e.g. Locust or k6 if
   you can justify the dependency per `CLAUDE.md` §3 — or a small asyncio/httpx
   script with none) against the local stack, covering report submission, the
   queue, the map bbox feed and analytics. Seed enough rows (thousands) to make
   the numbers mean something; `database/seeds` makes ~12 incidents.
2. **Measure before changing anything.** Use `EXPLAIN (ANALYZE, BUFFERS)` on the
   hot queries (queue, bbox, nearby, the Phase 14 aggregations — the latter scan
   `incidents` with no supporting index on `created_at`). Record the baseline in
   `docs/` so improvement is evidence.
3. **Index review** — likely candidates: `incidents(created_at)`,
   `dispatches(created_at)`; confirm with the plans, don't guess. Needs a migration
   (`0013`), applied/rolled back.
4. **Redis caching on hot reads** (Redis is already a dependency, used by rate
   limiting). Decide invalidation first; the queue and map must never show stale
   data during an incident — prefer a short TTL on aggregates (analytics), none on
   the live queue unless measured to matter.
5. Connection-pool tuning (`db_pool_size`, `db_max_overflow` exist in config).
   Partitioning and read replicas are deployment decisions; document, don't build.

Do **not** claim the NFR targets are met on the strength of a sandbox run.

---

## 4. Files changed since the V1 foundation

Everything below is committed. Nothing is staged or modified.

**Phase 7 — priority engine configuration**
- `backend/app/services/priority/engine.py` (PriorityWeights, registry, resolve)
- `backend/app/services/priority/config_loader.py` (new)
- `backend/app/core/config.py` (`priority_weights_version`, `priority_weights_path`)
- `backend/migrations/versions/0004_priority_engine_version.py` (new)
- `backend/tests/unit/test_priority_weights.py` (new)

**Phase 10 — resources**
- `backend/app/models/resource.py`, `repositories/resource_repository.py`,
  `services/resource_service.py`, `schemas/resource.py`,
  `api/v1/endpoints/resources.py` (all new)
- `backend/migrations/versions/0005_resources.py` (new)
- `backend/tests/integration/test_resources_api.py` (new)

**Phase 11 — dispatch + responder app**
- `backend/app/models/dispatch.py`, `repositories/dispatch_repository.py`,
  `services/dispatch_service.py`, `schemas/dispatch.py`,
  `api/v1/endpoints/dispatches.py` (all new)
- `backend/migrations/versions/0006_dispatches.py` (new)
- `apps/responder-web/**` (new Next.js app, port 3002)
- `packages/api-client/src/types.ts`, `client.ts`, `presentation.ts` (extended)
- `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/check.sh` (responder-web added)

**Phase 12 — hospitals**
- `backend/app/models/hospital.py`, `repositories/hospital_repository.py`,
  `services/hospital_service.py`, `schemas/hospital.py`,
  `api/v1/endpoints/hospitals.py` (all new)
- `backend/migrations/versions/0007_hospitals.py` (new)
- `backend/tests/integration/test_hospitals_api.py` (new)

**Phase 13 — notifications**
- `backend/app/models/notification.py`, `repositories/notification_repository.py`,
  `services/notification_service.py`, `services/notifiers.py`,
  `schemas/notification.py`, `api/v1/endpoints/notifications.py`,
  `utils/messages.py` (all new)
- `backend/migrations/versions/0008_notifications.py` (new)
- `backend/tests/integration/test_notifications_api.py` (new)
- `backend/app/services/incident_service.py`, `dispatch_service.py` (notify hooks)

**Phase 14 — analytics**
- `backend/app/repositories/analytics_repository.py` (new — every aggregation query)
- `backend/app/schemas/analytics.py` (new)
- `backend/app/services/analytics_service.py` (new — role gate, hotspot grid constant)
- `backend/app/api/v1/endpoints/analytics.py` (new)
- `backend/app/api/v1/router.py` (registered)
- `backend/tests/integration/test_analytics_api.py` (new)
- No migration — reads existing tables only.

**Phase 16 — security hardening**
- `backend/app/core/crypto.py`, `totp.py`; `backend/app/db/types.py` (new)
- `backend/app/services/scanners.py` (new); `auth_service.py`, `media_service.py`,
  `audit_service.py` (extended); `api/deps.py` (MFA policy), `api/v1/endpoints/auth.py`,
  `users.py`, `core/middleware.py`, `core/config.py`, `core/errors.py`, `core/logging.py`
- Models `user.py`, `incident.py`, `resource.py`, `hospital.py`; schemas `auth.py`,
  `user.py`, `media.py`; `repositories/hospital_repository.py` (decrypts raw SQL)
- Migrations `0009_account_lockout`, `0010_encrypt_contact_details`, `0011_mfa`,
  `0012_media_scan_status`
- Tests: `test_totp.py`, `test_crypto.py`, `test_scanners.py`, `test_mfa_api.py`,
  `test_account_recovery.py`, `test_contact_encryption.py`, and additions to
  `test_auth_api.py`, `test_media_api.py`, `test_health.py`
- Front ends: `packages/api-client` (`login(…, mfaCode?)`, `User.mfa_enabled`,
  `MediaItem.scan_status`), the three `AuthProvider`s and login pages, the three
  `next.config.ts` (CSP)
- `scripts/check.sh`, `.github/workflows/ci.yml`, `backend/requirements*.txt`
  (cryptography, pyotp, pip-audit; PyJWT bumped), `package-lock.json`
- Docs: `API.md`, `DATABASE.md`, `SECURITY.md`, `ROADMAP.md`, `RUNBOOK.md`,
  `.env.example`

---

## 5. Known issues, gaps and honest limits

**Not defects — deliberate, documented limits:**

1. **AI is a rule-based heuristic, not a trained model.** `ai/nlp/text_analyzer.py`
   is keyword and regex matching with confidence capped below certainty. A
   trained classifier needs a labelled dataset that does not exist. Swapping it
   changes nothing outside `ai/`.
2. **ETA is straight-line, not routing.** `estimate_minutes()` assumes 30 km/h
   over a direct line. It ignores roads, traffic and terrain, and every figure
   the API returns is labelled an estimate. Real routing (OSRM) is unbuilt.
3. **SMS/email/push transmit nothing.** `NullNotifier` records `UNAVAILABLE`
   with a reason. The requirement "never silently dropped" is met; actual
   delivery is not.
4. **Phase 15 (prediction) is skipped on purpose.** The roadmap itself says not
   to start without a real historical dataset. Do not build it on seed data.
5. **Analytics hotspot grid size (0.01°, ~1.1 km) is a fixed constant**
   (`HOTSPOT_GRID_DEGREES` in `analytics_service.py`), not configurable. If a
   future requirement needs a different resolution, change the one constant —
   do not let a caller pass an arbitrary cell size, or the coarsening
   guarantee becomes whatever the caller chooses.

**Real gaps to be aware of:**

6. **Docker has never been run.** No daemon in the dev sandbox. The Dockerfiles
   and `docker-compose.yml` are written and YAML-valid but **unbuilt and
   untested**, including the `responder-web` image. Verify with
   `docker compose up` before trusting them.
7. **Netlify deployment was requested but not done.** See §7 below — it needs a
   decision from you first, because Netlify cannot host this backend.
8. **`eslint-config-next@16.3.5` is incompatible with ESLint 10** (its bundled
   `eslint-plugin-react` calls the removed `context.getFilename`). ESLint is
   pinned to `^9.39.5` in all three apps. Do not bump it without testing.
9. **A lint failure slipped through once before** (documented in the prior
   checkpoint; already fixed) because output was being tailed instead of exit
   codes read. **Always run `./scripts/check.sh` and read its actual final
   line** (`All checks passed.` or `Failed: ...`) — this checkpoint's own
   verification caught two real ruff/black failures in the analytics module
   this same way, and both are now fixed.
10. **Dispatch does not auto-advance the incident's status.** Sending a unit
    leaves the incident where it is, because `REPORTED → ASSIGNED` is not a
    legal transition and forcing it would violate the state machine. The
    dispatcher moves the incident separately. This is intentional; revisit
    only with a deliberate state-machine change.
11. Seed data (`database/seeds/seed_development.py`) creates users and
    incidents only — **no resources, hospitals or dispatches**. Demoing
    Phases 10–14 needs those created through the API first, and analytics
    will read as empty/zero until some dispatches and resolutions exist.
12. ~~No endpoint smoke-tested against a live server.~~ Partly addressed: sign-in,
    dashboard, map and the MFA path were run in a real browser against the live
    stack (§1). **Resources, dispatch, hospitals, notifications and analytics
    were still only exercised through the test suite**, not through a UI/live run.
13. **Phase 16 is not finished by its code.** No penetration test, no operating
    authority acceptance. `docs/SECURITY.md` §12 lists every other gap: no MFA
    enrolment UI or recovery codes; front-end CSP keeps `'unsafe-inline'`;
    ClamAV client untested against a real ClamAV; MFA enforcement off by default;
    dev-tooling advisory (`braces`) not gating.
14. **The browser end-to-end scripts are not in the repository.** They were
    throwaway scratchpad files (`playwright-core` + the sandbox Chromium at
    `/opt/pw-browsers/chromium`). A committed `scripts/smoke` would turn a
    one-off check into a regression guard; it needs a decision on the browser
    dependency.
15. **Seeded dev accounts are not MFA-enrolled and `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL`
    is false in development**, so the shipped dev stack does not exercise the
    enforcement path. Turn it on in staging and enrol the accounts.
16. **The `npm audit` gate needs network access**, as does `pip-audit`. Offline,
    `./scripts/check.sh` fails on those two steps for a reason unrelated to the code.
17. **Lockout reveals that an account exists** (`403 ACCOUNT_LOCKED`) and can be
    triggered on purpose against a victim; the cap and admin unlock bound it.

---

## 6. Commands to restart the project

```bash
cd /home/user/raksha-net-ai

# 1. Postgres (the sandbox container stops it on restart)
sudo pg_ctlcluster 16 main start && pg_isready

# 2. Environment for any backend command (development derives the encryption
#    key from the secret; staging/production need RAKSHA_ENCRYPTION_KEY)
export RAKSHA_ENVIRONMENT=development \
       RAKSHA_SECRET_KEY=dev-secret-key-at-least-32-chars-long-xxxx \
       RAKSHA_AI_ENABLED=true \
       RAKSHA_RATE_LIMIT_ENABLED=false \
       POSTGRES_USER=raksha POSTGRES_PASSWORD=raksha_dev_password \
       POSTGRES_DB=raksha_net_ai POSTGRES_HOST=localhost

# 3. Schema + data
cd backend && .venv/bin/alembic upgrade head && cd ..
PYTHONPATH="$PWD/backend:$PWD" backend/.venv/bin/python database/seeds/seed_development.py

# 4. Run it
./scripts/dev_backend.sh                           # API on :8000
npm run dev:citizen                                # :3000
npm run dev:control                                # :3001
npm run dev --workspace @raksha/responder-web      # :3002
```

**Verify everything still passes:**

```bash
./scripts/check.sh            # the full gate — read the LAST line
cd backend && .venv/bin/pytest -q          # 407 backend tests
cd .. && PYTHONPATH=. backend/.venv/bin/pytest ai/tests -q   # 31 AI tests
```

For test runs, use `RAKSHA_ENVIRONMENT=test` (not `development`) and a
`test-secret-key-...` value — see `backend/tests/conftest.py` for the exact
defaults it sets via `os.environ.setdefault`, which is also what
`./scripts/check.sh` relies on.

**Migration round-trip** (do this after any model change):

```bash
cd backend
.venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head
```

Seeded accounts — password `raksha-development-only`:
`citizen@raksha.example`, `dispatcher@raksha.example`, `responder@raksha.example`,
`hospital@raksha.example`, `admin@raksha.example`.

Note: the dev sandbox is ephemeral. If `backend/.venv` is missing after a
restart, recreate it with
`cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`.

---

## 7. Outstanding request: Netlify deployment

You asked for this and it is **still not done**, because it needs a decision
only you can make. Unchanged since the last checkpoint.

**Netlify can host the three Next.js front ends. It cannot host this backend.**
Netlify runs static sites and short-lived serverless functions — not a
long-running FastAPI process with a persistent PostgreSQL + PostGIS database,
Redis, and a media volume. Deploying only the front ends gives you three apps
that load and then fail every API call, unless the backend is hosted elsewhere
and `NEXT_PUBLIC_API_BASE_URL` points at it.

**The decision to make when you return:**

- **Option A** — deploy the front ends to Netlify now and host the backend
  separately (Railway, Render, Fly.io — each supports PostGIS and a long-running
  process). Then set `NEXT_PUBLIC_API_BASE_URL` per site and redeploy.
- **Option B** — deploy the front ends to Netlify as a UI preview only,
  understanding that API calls will fail until a backend exists.
- **Option C** — pick a single host that can run everything, and skip Netlify.

A Netlify MCP connector was available in the session. Deploying will also need
you to confirm which Netlify account/team to use.

---

## 8. Suggested order when you return

1. **Phase 17 (Performance)** — §3. Measure first; be honest about what a sandbox shows.
2. **Phase 18 (Production readiness artifacts)** — a `/metrics` endpoint,
   backup/restore scripts, deployment docs. Without claiming a cloud deployment
   happened.
3. **Decide Netlify (§7)** and deploy.
4. **The human half of Phase 16** — commission a penetration test; get the
   residual risk accepted; then (optionally) add the MFA enrolment UI, recovery
   codes, and a nonce-based CSP. None of that is a substitute for the first two.
5. A committed browser smoke test (§5, item 14), and a live pass over resources,
   dispatch, hospitals, notifications and analytics.

Phases 8, 9 and 15 stay blocked on inputs that do not exist (a labelled photo
dataset, an ASR provider, a real historical dataset). Do not fake any of them.
