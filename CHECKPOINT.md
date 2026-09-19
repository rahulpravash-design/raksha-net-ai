# CONTINUE FROM HERE

**Checkpoint date:** 2026-09-19
**Branch:** `claude/raksha-net-ai-development-5uyq42`
**Last commit:** `7d42dd7 feat(analytics): add response-time, resolution, category and resource metrics with coarsened hotspots`
**State:** Clean. Working tree empty, every check green, everything pushed.

> Read this file, then `docs/ROADMAP.md`, then `CLAUDE.md`. Do not redesign
> anything marked COMPLETE below — it is built, tested and verified.

---

## 1. Where the project stands

**Phases 0–14 are implemented, except Phases 8 and 9.**

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
| 16 Security hardening | ⬜ **next** |
| 17 Performance & scale | ⬜ not started |
| 18 Production readiness | ⬜ not started |

**Verification at checkpoint time** — all of this was run, not assumed:

- `./scripts/check.sh` — **18/18 steps green** (ruff, black, mypy, pytest, AI
  pytest, then eslint + tsc + vitest + build for all three front ends). Read
  from its actual final line (`All checks passed.`), not by tailing
  individual step output.
- **336 backend tests** (327 + 9 new for analytics), **31 AI tests**, **89
  frontend tests** (44 citizen, 40 control centre, 5 responder). 456 total,
  all passing.
- No migration was needed for Phase 14 — every query reads existing tables.
  The Alembic chain is unchanged since the last checkpoint (`0001 → 0008`,
  previously verified down to base and back up with no orphaned enum types).
- 254 tracked files (253 plus this checkpoint update), 27 commits, 63 API
  endpoints (58 + 5 analytics), 8 migrations.

---

## 2. Current working feature — finished, nothing half-done

Phase 14 (analytics) was the last thing built and it is **committed and
complete**. There is no partially-written code anywhere.

What it delivered: five read-only endpoints under `/api/v1/analytics`,
restricted to dispatch-capable roles (`DISPATCHER`, `ADMIN`, `SUPER_ADMIN`):

- `GET /analytics/response-time` — minutes from report to first dispatch
  (sample size, mean, median, min, max), filterable by `since`/`until`/`category`.
- `GET /analytics/resolution-time` — minutes from report to resolved, same shape.
- `GET /analytics/category-breakdown` — counts and average priority score per category.
- `GET /analytics/resource-utilization` — active/available counts and
  dispatches-in-period, per resource type.
- `GET /analytics/hotspots` — incident clustering on a **coarsened ~0.01°
  (~1.1 km) grid**, never a raw incident coordinate.

**The rule the hotspot endpoint exists to enforce** (`CLAUDE.md` section 5:
"analytics surfaces aggregated or coarsened location") is implemented at the
SQL layer, not just documented: coordinates are rounded in PostgreSQL
`numeric` (exact decimal) space — `ROUND(latitude / 0.01) * 0.01` — before
the row ever leaves `AnalyticsRepository.hotspots()`, so no code path can
accidentally forward a precise coordinate. A test
(`test_hotspots_never_return_a_raw_incident_coordinate`) reports two
incidents at different points inside the same grid cell and asserts the
single returned hotspot's coordinates equal neither report's own position.

Two non-obvious things fixed along the way, in case a similar query is
written later:

1. **Never alias a computed column with the same name as the source table's
   real column** (I used `AS latitude`/`AS longitude` for the rounded value,
   which collides with `incidents.latitude`/`longitude`). `GROUP BY` then
   resolved the alias back to the *raw* input column instead of the rounded
   expression, silently defeating the coarsening. Fixed by grouping on the
   grid-index expression directly and wrapping the returned coordinate in
   `MIN(...)` (safe, since every row in a group has an identical computed
   value).
2. Ruff's `S608` (SQL-injection heuristic) flagged an f-string used only to
   splice together two *static* SQL fragments — a false positive, since
   nothing interpolated was ever request-derived. Fixed by inlining the
   shared fragment instead of leaving an f-string for a human to reread and
   wonder about; there is no `# noqa` in this codebase for something that
   can just as easily be made unambiguous.

---

## 3. The exact next step

**Start Phase 16 — Security hardening.** (Phase 15/prediction stays skipped
— see `docs/ROADMAP.md`'s own gate: no real historical dataset exists.) From
`docs/ROADMAP.md`:

> MFA for operational roles, upload antivirus scanning, column-level
> encryption of contact details, account lockout, full security headers and
> CSP, dependency audit gating, penetration test and remediation.
>
> **This phase gates any real-world pilot.**

**Read this carefully before starting:** a real penetration test and formal
sign-off by an operating authority (this phase's own gate, and Phase 18's)
are human acts. An agent session cannot perform or claim either. What *can*
be honestly built this phase:

1. **Account lockout** — extend `app/services/auth_service.py` /
   `app/repositories/user_repository.py` with a failed-attempt counter and a
   time-boxed lock, audited via `AuditAction` the same way login events
   already are. Migration needed (new columns on `users`).
2. **TOTP MFA for operational roles** — a `mfa_secret` column (encrypted, see
   next item), enrollment and verification endpoints, and a login flow that
   requires a second factor for `DISPATCH_ROLES`/`OPERATIONAL_ROLES`.
   Migration needed.
3. **Column-level encryption of contact details** — `Incident.contact_phone`,
   `Resource.contact_phone`, `Hospital.contact_phone` are plaintext today.
   Decide an approach (application-level AES via a new `app/core/crypto.py`
   keyed from `RAKSHA_SECRET_KEY` or a dedicated key, vs. `pgcrypto`) and
   write it down before touching the schema — this is exactly the kind of
   decision `CLAUDE.md` section 9 asks to plan before implementing.
4. **Security headers & CSP** — middleware in `app/main.py`, no migration.
   Should be fast to add and easy to verify with a direct HTTP test.
5. **Dependency audit gating** — add `pip-audit` (backend) and `npm audit`
   (frontends) to `scripts/check.sh` and CI, failing the gate on a known-high
   vulnerability. Check current dependencies aren't already flagged before
   wiring the gate, or the very first run fails on pre-existing debt that
   isn't this phase's to fix blind.
6. **What to explicitly *not* claim done**: write a short, honest section in
   `docs/SECURITY.md` (or update the existing one) stating that a real
   penetration test has not been performed and this deployment has not been
   accepted by an operating authority — mirroring how `docs/ROADMAP.md`
   already handles Phase 15. Do not let the presence of MFA/lockout/CSP code
   imply otherwise.

Write tests for every new endpoint (happy path, validation failure,
unauthenticated, wrong-role) exactly as every prior phase did, plus the
account-lockout and MFA-bypass-attempt cases specifically.

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
12. **No analytics endpoint has been smoke-tested against a live server** —
    only through the integration test suite (real PostgreSQL, but via
    `TestClient`, not an actual running `uvicorn` process). Low risk, since
    the pattern is identical to every prior phase's endpoints, but flagged
    for completeness.

---

## 6. Commands to restart the project

```bash
cd /home/user/raksha-net-ai

# 1. Postgres (the sandbox container stops it on restart)
sudo pg_ctlcluster 16 main start && pg_isready

# 2. Environment for any backend command
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
cd backend && .venv/bin/pytest -q          # 336 backend tests
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

1. **Phase 16 (Security hardening)** — the natural next step; see §3 for the
   concrete breakdown and what cannot honestly be claimed done by an agent
   (a real penetration test, operating-authority acceptance).
2. **Phase 17 (Performance)** — Redis caching on hot reads, index review, and a
   load-test script that can actually be run against the local stack.
3. **Phase 18 (Production readiness artifacts)** — metrics endpoint,
   backup/restore scripts, deployment docs, without claiming actual cloud
   deployment.
4. **Deployment** — once §7 is decided.

Phases 8, 9 and 15 stay blocked on inputs that do not exist (a labelled photo
dataset, an ASR provider, a real historical dataset). Do not fake any of them.
