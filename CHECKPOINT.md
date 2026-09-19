# CONTINUE FROM HERE

**Checkpoint date:** 2026-09-19
**Branch:** `claude/raksha-net-ai-development-5uyq42`
**Last commit:** `357b462 feat(notifications): add the in-app inbox with per-channel delivery records`
**State:** Clean. Working tree empty, every check green, everything pushed.

> Read this file, then `docs/ROADMAP.md`, then `CLAUDE.md`. Do not redesign
> anything marked COMPLETE below — it is built, tested and verified.

---

## 1. Where the project stands

**Phases 0–13 are implemented, except Phases 8 and 9.**

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
| 14 Analytics | ⬜ **next** |
| 15 Prediction | ⬜ deliberately skipped — no historical dataset exists |
| 16 Security hardening | ⬜ not started |
| 17 Performance & scale | ⬜ not started |
| 18 Production readiness | ⬜ not started |

**Verification at checkpoint time** — all of this was run, not assumed:

- `./scripts/check.sh` — **18/18 steps green** (ruff, black, mypy, pytest, AI
  pytest, then eslint + tsc + vitest + build for all three front ends).
- **327 backend tests**, **31 AI tests**, **89 frontend tests** (44 citizen,
  40 control centre, 5 responder). 447 total, all passing.
- Full Alembic chain `0001 → 0008` verified **down to base and back up** with
  no orphaned enum types.
- 247 tracked files, 24 commits, 58 API endpoints, 8 migrations.

---

## 2. Current working feature — finished, nothing half-done

Phase 13 (notifications) was the last thing built and it is **committed and
complete for its in-app scope**. There is no partially-written code anywhere.

What Phase 13 delivered: an in-app inbox scoped strictly to its recipient;
notifications fired on incident status change (to the reporter) and on dispatch
assignment/stand-down (to the crew); nobody notified about their own action;
per-channel delivery records; unread counts and read marking.

What it deliberately did **not** deliver, and must be picked up when a provider
exists: real SMS/email/push transmission, delivery retries, and per-channel
opt-out preferences.

---

## 3. The exact next step

**Start Phase 14 — Analytics.** From `docs/ROADMAP.md`:

> Response-time and resolution metrics, category breakdowns, resource
> utilisation, and hotspot detection on **coarsened** coordinates.

Concretely, in this order:

1. `backend/app/repositories/analytics_repository.py` — aggregation queries.
   Response time = `dispatches.created_at − incidents.created_at`; resolution
   time = `incidents.resolved_at − incidents.created_at`. Resource utilisation
   comes from `dispatches` joined to `resources`.
2. `backend/app/schemas/analytics.py` — response shapes.
3. `backend/app/services/analytics_service.py` — role gate (operational roles;
   consider restricting to dispatch/admin) and the coarsening rule.
4. `backend/app/api/v1/endpoints/analytics.py` — register in
   `backend/app/api/v1/router.py`.
5. `backend/tests/integration/test_analytics_api.py`.

**The one rule that must not be broken here.** `CLAUDE.md` §5: *"Precise
citizen location is available to operational roles only; analytics surfaces
aggregated or coarsened location."* Hotspot output must snap coordinates to a
grid (~0.01°, roughly 1 km) or aggregate by cell count — **never** return a raw
incident coordinate from an analytics endpoint. Write the test that asserts
this before writing the endpoint.

No migration is expected for Phase 14 — it reads existing tables.

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

**Real gaps to be aware of:**

5. **Docker has never been run.** No daemon in the dev sandbox. The Dockerfiles
   and `docker-compose.yml` are written and YAML-valid but **unbuilt and
   untested**, including the new `responder-web` image. Verify with
   `docker compose up` before trusting them.
6. **Netlify deployment was requested but not done.** See §7 below — it needs a
   decision from you first, because Netlify cannot host this backend.
7. **`eslint-config-next@16.3.5` is incompatible with ESLint 10** (its bundled
   `eslint-plugin-react` calls the removed `context.getFilename`). ESLint is
   pinned to `^9.39.5` in all three apps. Do not bump it without testing.
8. **A lint failure slipped through earlier** because output was being tailed
   instead of exit codes read (a blind `pytest.raises(Exception)`). Fixed in
   `357b462`. **Run `./scripts/check.sh` and read its final line** rather than
   tailing individual commands.
9. **Dispatch does not auto-advance the incident's status.** Sending a unit
   leaves the incident where it is, because `REPORTED → ASSIGNED` is not a legal
   transition and forcing it would violate the state machine. The dispatcher
   moves the incident separately. This is intentional; revisit only with a
   deliberate state-machine change.
10. Seed data (`database/seeds/seed_development.py`) creates users and incidents
    only — **no resources, hospitals or dispatches**. Demoing Phases 10–13 needs
    those created through the API first.

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
cd backend && .venv/bin/pytest -q          # 327 backend tests
cd .. && PYTHONPATH=. backend/.venv/bin/pytest ai/tests -q   # 31 AI tests
```

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

You asked for this and it is **not done**, because it needs a decision only you
can make.

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

1. **Phase 14 (Analytics)** — the natural next step, no external dependencies,
   ~1 session. Details in §3.
2. **Phase 16 (Security hardening)** — TOTP MFA, account lockout, security
   headers/CSP, contact-detail encryption. Note: a real penetration test and
   Phase 18's "formal acceptance by an operating authority" are human acts that
   cannot be completed by an agent; they can only be prepared for.
3. **Phase 17 (Performance)** — Redis caching on hot reads, index review, and a
   load-test script that can actually be run against the local stack.
4. **Deployment** — once §7 is decided.

Phases 8, 9 and 15 stay blocked on inputs that do not exist (a labelled photo
dataset, an ASR provider, a real historical dataset). Do not fake any of them.
