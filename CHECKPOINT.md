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
but its penetration test and risk acceptance have NOT happened. Phase 17 is
measured and fixed in a development environment only.**

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
| 17 Performance & scale | ⚠️ measured + fixed in a dev environment; **no production capacity evidence** |
| 18 Production readiness | ⬜ **next** |

**Verification at checkpoint time** — all of this was run, not assumed:

- `./scripts/check.sh` — **20/20 steps green** (ruff, black, mypy, pytest, the
  migration chain + model-drift check, AI pytest, pip-audit, npm audit, then
  eslint + tsc + vitest + build for all three front ends). Read from its actual
  final line (`All checks passed.`).
- **413 backend tests**, **31 AI tests**, **90 frontend tests** (45 citizen, 40
  control centre, 5 responder). 534 total, all passing. The backend suite was run
  twice in a row to confirm one flaky test was really fixed.
- Migrations `0001 → 0013`; the gate now upgrades to head, fails on model/migration
  drift, and downgrades to base on every run.
- Load results (`docs/PERFORMANCE.md`): 100k incidents; queue p95 283 ms and report
  p95 180 ms against 1,500 / 500 ms targets — **on one shared development machine**.
- Earlier this phase-set: a live Chromium run of sign-in, dashboard and the MFA path
  against the running stack (scripts not in the repo; see §5, item 14).
- 272 tracked files, 13 migrations, 68 API operations, 41 commits.

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

**Phase 17 (performance)** was done after that. Full record: `docs/PERFORMANCE.md`.

- Both PRD targets met on dev hardware by a wide margin (queue p95 283 ms vs 1,500;
  report p95 180 ms vs 500) at 100k incidents.
- **Found and fixed an overload deadlock**: ~64 concurrent clients made the API
  collapse (56 errors, 31 s p95, ending as 500s). Cause: a request holds a DB
  connection while waiting for a worker thread. Fix: `ConcurrencyLimitMiddleware`
  (24 in flight, queue 3 s, then `503` + `Retry-After`), 5 s pool timeout, pool
  exhaustion → `503`. Verified: 0 errors at 8/32/64/128 workers.
- `incidents(created_at)` index (migration 0013): deep history paging 481 → 170 ms.
- No caching (measured, not needed). `dispatches(created_at)` index tried, rejected.
- `scripts/check_migrations.sh` + `alembic check` now gate model/migration drift
  (it found 3 real drifts, and was shown to fail when a model drifts).
- A flaky test (`test_the_spatial_index_is_used...`) failed by planner-statistics
  timing; made deterministic.
- **My first load data was wrong** (an uncorrelated `LATERAL` is evaluated once in
  Postgres, so every row got the same values) and the first numbers were thrown
  away. Verify generated data varies before trusting a measurement.

Two lessons, in case the pattern recurs:

1. **`ruff S608` flags any f-string passed to `text()`**, even over static
   fragments. Don't suppress it; write static SQL (done in analytics, the
   encryption tests and migration 0010).
2. **A SQL alias that shares a column's name makes `GROUP BY` bind the raw
   column** (the Phase 14 hotspot bug). Group on the expression.

---

## 3. The exact next step

**Start Phase 18 — Production readiness.** From `docs/ROADMAP.md`: managed
infrastructure, secret management, observability, backup and rehearsed restore,
release pipeline with rollback, runbooks, and formal acceptance by an operating
authority.

Much of that is organisational or needs real infrastructure and **cannot be
completed or claimed from a development session** (managed infrastructure, a
rehearsed restore in a real environment, the authority's acceptance). What can be
built and tested honestly here, in this order:

1. **A `/metrics` endpoint** (Prometheus text format): request rate and latency
   histogram per route, error rate, DB pool usage, and the new overload signals
   (requests queued/shed by `ConcurrencyLimitMiddleware`, pool exhaustion).
   `docs/DEPLOYMENT.md` §8 already promises these. Decide whether a client library
   (`prometheus-client`) is justified per `CLAUDE.md` §3, and keep the endpoint
   restricted — it must not be public. The shed/queue counters are the thing
   that would have shown the Phase 17 deadlock early.
2. **Backup and restore scripts** (`pg_dump`/WAL guidance) that can actually be
   run against the local Postgres, **with a restore verified end to end** into a
   scratch database: restore, then compare row counts and run the readiness probe.
   Encrypted columns need the matching `RAKSHA_ENCRYPTION_KEY` — state that.
3. **Readiness that means something**: `/health/ready` currently checks the
   database and PostGIS; consider Redis and the scanner as *degraded*, not down.
4. **Release/rollback notes tied to migrations** — which migrations reverse
   losslessly (all do, and the gate proves it on empty data; `0010` rewrites data).
5. **Do not** claim a cloud deployment, a rehearsed production restore, or
   operating-authority acceptance. Write the procedures; leave the boxes unticked.

Then the outstanding **Netlify decision (§7)**.

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

**Phase 17 — performance**
- `database/seeds/seed_load.py`, `scripts/loadtest.py`, `scripts/check_migrations.sh` (new)
- `backend/app/core/middleware.py` (`ConcurrencyLimitMiddleware`), `core/errors.py`
  (`ServiceBusyError`, pool-timeout handler), `core/config.py`, `db/session.py`, `main.py`
- `backend/migrations/versions/0013_incident_created_at_index.py`; models `incident.py`,
  `user.py` (server defaults declared)
- Tests: `tests/unit/test_overload.py`; `test_geo_api.py` made deterministic
- Docs: `docs/PERFORMANCE.md` (new), `TESTING.md` §8, `DEPLOYMENT.md` (sizing)

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
18. **Phase 17 has no production evidence.** One shared 4-core machine; see
    `docs/PERFORMANCE.md` §6. Re-run `scripts/loadtest.py` from a separate machine
    against a production-shaped deployment before stating any capacity.
19. **Unexplained sporadic `ReadError` with several API processes** (~1–2 of 370
    requests; none with one process; nothing in the server log). Probably a
    keep-alive race. Understand it before running several processes in earnest.
20. **Postgres `max_connections` (default 100)** limits API processes to three at
    full pool use; `processes × 30` must fit. Documented in DEPLOYMENT.md.

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

1. **Phase 18 (Production readiness artifacts)** — §3. Metrics, a *verified*
   backup/restore, honest readiness. Claim no deployment or acceptance.
2. **Decide Netlify (§7)** and deploy.
3. **The human half of Phase 16** — commission a penetration test; get the
   residual risk accepted; then (optionally) the MFA enrolment UI, recovery
   codes, a nonce-based CSP.
4. **The human half of Phase 17** — run the load test from a separate machine
   against a production-shaped deployment.
5. A committed browser smoke test (§5, item 14), and a live pass over resources,
   dispatch, hospitals, notifications and analytics.

Phases 8, 9 and 15 stay blocked on inputs that do not exist (a labelled photo
dataset, an ASR provider, a real historical dataset). Do not fake any of them.
