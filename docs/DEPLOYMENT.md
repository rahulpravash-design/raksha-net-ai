# RAKSHA NET AI — Deployment Architecture

---

## 1. Environments

| Environment | Purpose | Data | Deploy trigger |
|---|---|---|---|
| `development` | Local work | Synthetic seeds | `docker compose up` |
| `test` | CI | Ephemeral, per-run | Every push / PR |
| `staging` | Pre-production verification | Synthetic, production-shaped | Merge to `develop` |
| `production` | Live | Real | Tagged release, manual approval |

`RAKSHA_ENVIRONMENT` drives environment-specific behaviour. In any environment
other than `development` the application **refuses to start** if
`RAKSHA_DEBUG=true`, `SECRET_KEY` is the placeholder, or CORS is `*`.

## 2. Local development

```bash
cp .env.example .env          # then edit POSTGRES_PASSWORD and RAKSHA_SECRET_KEY
docker compose up -d db redis
docker compose up backend citizen-web control-center
```

| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Citizen web | http://localhost:3000 |
| Control centre | http://localhost:3001 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

Without Docker: run PostgreSQL 16 with the PostGIS extension locally, point
`RAKSHA_DATABASE_URL` at it, then `scripts/bootstrap_backend.sh` and
`scripts/dev_backend.sh`.

## 3. Container topology

```
                    ┌──────────────┐
  browser ─── 443 ──│ reverse proxy│── /api ──► backend (uvicorn, N replicas)
                    │  nginx/ALB   │──  /   ──► citizen-web (Next.js)
                    └──────────────┘──/ops──► control-center (Next.js)
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                              PostgreSQL       Redis      object storage
                              + PostGIS
```

- Backend image: `python:3.11-slim`, non-root user, uvicorn behind the proxy.
- Frontend images: Next.js standalone output, non-root.
- Database: a managed PostgreSQL with PostGIS in staging and production — never
  a container holding a volume on a single host.

## 4. Configuration and secrets

All configuration is environment variables (`.env.example` is the catalogue).
Secrets in staging and production come from a managed secret store injected at
runtime — never baked into an image, never committed.

Rotation: `SECRET_KEY` rotation invalidates access tokens within their 30-minute
TTL; refresh tokens are unaffected because they are opaque and stored.

## 5. Database migrations

```bash
cd backend
alembic upgrade head              # apply
alembic revision --autogenerate -m "feat(db): add resources"
alembic downgrade -1              # roll back one revision
```

Deployment order: migrate, then release application code. Migrations must be
backward compatible with the running version (expand/contract):

1. Release N: add the column, write to both, read the old one.
2. Release N+1: read the new one.
3. Release N+2: drop the old one.

Every migration is tested by applying and rolling back against a copy of a
staging snapshot before it reaches production.

## 6. CI/CD

`.github/workflows/ci.yml` on every push and pull request:

```
backend:   ruff → black --check → mypy → pytest (against a PostGIS service)
frontend:  npm ci → lint → typecheck → test → build
security:  pip-audit → npm audit
```

Release pipeline (Phase 18): build and scan images, push to the registry,
deploy to staging, run smoke tests, then a manually approved production
deploy with an automatic rollback on failed health checks.

## 7. Health checks and probes

| Probe | Endpoint | Meaning |
|---|---|---|
| Liveness | `GET /api/v1/health` | Process is up |
| Readiness | `GET /api/v1/health/ready` | Database reachable; ready for traffic |

The readiness probe returns `503` when the database is unreachable, so the
orchestrator removes the instance from the load balancer instead of serving
errors.

## 8. Observability

| Signal | Tooling |
|---|---|
| Logs | Structured JSON to stdout, shipped by the platform, correlation ID per request |
| Metrics | **Built:** `GET /metrics` (Prometheus text, bearer-token protected, absent unless `RAKSHA_METRICS_TOKEN` is set): request rate and latency histogram per route template, in-flight requests, DB pool use, open/unassigned incidents, and requests queued/shed. Series and alerts: runbook. **Not built:** a Prometheus/Grafana deployment, dashboards, alert rules |
| Traces | OpenTelemetry — **not built** |
| Errors | Sentry or equivalent, with PII scrubbing |
| Uptime | External probe against `/health/ready` |

Alerts that page: readiness failing, error rate > 2% over 5 minutes, p95 report
latency > 2 s, database connection saturation, disk > 85%.

## 9. Backup and recovery

- **Built and tested:** `scripts/backup.sh`, `restore.sh` and `verify_restore.sh`
  (age-encrypted, checksummed, media included; procedure in the runbook). On a
  100,000-incident database a backup took 3 s and a verified restore 4 s on a
  development machine.
- **Stated targets, not demonstrated:** RPO 15 minutes and RTO 1 hour. A logical
  dump gives an RPO equal to the interval between backups; 15 minutes needs
  continuous WAL archiving / point-in-time recovery on the database platform, which
  is infrastructure this repository cannot provide or prove. The RTO has not been
  measured on production-sized data or hardware.
- Restores must be rehearsed (quarterly) from real backups in an isolated
  environment; `verify_restore.sh` makes that a one-command check. A backup that has
  never been restored is not a backup.
- `RAKSHA_ENCRYPTION_KEY` is not in any backup and must be kept separately; without
  it the encrypted phone numbers and MFA secrets cannot be recovered.
- Media object storage uses versioning and lifecycle rules (deployment).
- The disaster-recovery runbook lives in `infrastructure/deployment/`.

## 10. Scaling path

| Pressure | Response |
|---|---|
| API CPU | Horizontal replicas behind the proxy (the backend is stateless) |
| Read load | PostgreSQL read replicas for analytics and map queries |
| Media | Object storage with a CDN in front |
| AI latency | Move analysis to a Celery worker pool; the API stays async |
| Real-time fan-out | Redis pub/sub behind the WebSocket layer |
| Write load | Partition `incidents` and `audit_logs` by month |

### Sizing a deployment (measured — see `PERFORMANCE.md`)

- One API process is CPU-bound at roughly 40 dashboard refreshes/s or 55 report
  submissions/s on development hardware; throughput scales with processes.
- Each process may open `RAKSHA_DB_POOL_SIZE + RAKSHA_DB_MAX_OVERFLOW` (30)
  connections. Keep `processes × 30` under PostgreSQL `max_connections` (default
  100): three processes per default database, or raise it / add PgBouncer.
- `RAKSHA_MAX_CONCURRENT_REQUESTS` (24) must stay below the pool total and the
  worker-thread count. Above it requests queue for up to 3 s, then receive
  `503 SERVICE_BUSY` with `Retry-After`; the proxy and clients should honour it.
- Rate limiting is per process unless `RAKSHA_RATE_LIMIT_BACKEND=redis`; behind several processes set it (see `SECURITY.md` §7).
- **The front ends render every page per request** (each carries a fresh CSP nonce, `SECURITY.md` §6). Do not put a CDN or proxy cache in front of their HTML — a cached page would serve one visitor's nonce to everyone and its scripts would be refused. Static assets under `/_next/static/` are fine to cache. Size the Node processes for server rendering on every page view, not for serving prerendered files; this was not load-tested.

## 11. Production readiness status

An honest account of each item: what the repository provides, and what only a real
deployment (or a person) can supply. Nothing here has been deployed.

| Item | In this repository | Still needed |
|---|---|---|
| Managed PostgreSQL + PostGIS, encrypted at rest | — | The platform; not provisioned |
| Secrets in a managed store | Config reads the environment; startup refuses placeholder/missing secrets in production | A secret store, and putting the secrets in it |
| TLS, HSTS, security headers | API and front-end headers + CSP; nginx example | Termination and certificates; verify on the real host |
| CORS restricted | **Enforced at startup** in staging/production | — |
| Rate limiting backed by Redis | `RAKSHA_RATE_LIMIT_BACKEND=redis` shares counters across processes (tested against a real Redis and across two real processes); falls back to local counting if Redis fails, with a metric | A Redis for the deployment, and setting the backend to `redis` (the default is `memory`) |
| Migrations applied and verified | Gate: chain up/down, drift check; `0010` proven on planted data | Rehearsal on a restored production copy (`RELEASE.md`) |
| Container images | Four images; built and the compose stack run end to end once in a sandbox (non-root, health checks, migrations from empty, browser suite green — `CHECKPOINT.md` §5 item 6). The backend image installs no OS packages | A registry, image scanning, and a run on the real host |
| Health probes wired | Liveness + readiness (DB, PostGIS, schema state); container health check (stdlib Python, no curl) | Wiring in the orchestrator |
| Log shipping, metrics, alerting | Structured logs; `/metrics`; alert suggestions in the runbook | A collector, dashboards, alert rules, paging |
| Backups running; restore rehearsed | Scripts + `verify_restore.sh`, rehearsed locally | A schedule, off-site storage, key custody; a rehearsal in the real environment |
| Penetration test, findings closed | — | **A person.** Not done |
| AI evaluation thresholds | n/a (rule-based baseline) | If a trained model is ever enabled |
| Incident-response runbook signed off | `RUNBOOK.md` (technical) | Sign-off by the responsible people |
| Release pipeline with rollback | CI; `RELEASE.md` (manual procedure) | A deploy pipeline; a rehearsal |
| **Operating authority has accepted the residual risk** | — | **A person. Not done** |

The last row is not ceremonial. This platform must not carry real emergency traffic
until a responsible authority has accepted it.

---

## 12. Email (password recovery)

Optional. Set `RAKSHA_SMTP_HOST` (+ port, credentials, `RAKSHA_SMTP_SECURITY=starttls|ssl`)
and the three `RAKSHA_*_APP_URL` values (https). Staging/production refuse to start with
unencrypted SMTP or http links while email is on. Leave it unset and the platform runs
without recovery email: the sign-in screens say so and point to an administrator.

* Use a sending domain with SPF/DKIM so recovery mail is not filed as spam — the most
  common reason recovery "does not work", and nothing in the application can detect it.
* To try it locally: `python scripts/dev_mailbox.py --port 1025 --dir /tmp/mailbox`, then
  start the API with `RAKSHA_SMTP_HOST=127.0.0.1 RAKSHA_SMTP_PORT=1025
  RAKSHA_SMTP_SECURITY=none`. The mailbox accepts everything and never relays; each message
  lands in the directory as JSON.
* Verified against that mailbox only. **No real mail provider has been tried**, and the
  STARTTLS/SSL paths are covered by selection logic, not against a live TLS server.

---

## 13. Netlify (front ends) and the backend host (Render)

Netlify hosts the three Next.js apps; it cannot host the backend (a long-running FastAPI
process with PostgreSQL + PostGIS, an optional Redis and an uploads volume). The backend
runs on a host that can run `backend/Dockerfile`; this section is written for **Render**,
whose managed PostgreSQL lists PostGIS as a supported extension.

**Status: nothing is deployed.** What is established and what is not is listed in 13.9.
Whatever is deployed from this guide is a **demonstration or controlled pilot**: there has
been no independent penetration test and no acceptance by an operating authority
(`SECURITY.md` §12). Do not use it for real emergencies.

```
browser ── HTTPS ──► Netlify (control centre / citizen / responder)
   │
   └─ HTTPS, direct (CORS) ──► Render web service (backend/Dockerfile, uvicorn :8000)
                                  ├─► Render PostgreSQL (PostGIS)
                                  ├─► Render Key Value (Redis-compatible, rate limits only)
                                  └─► persistent disk (uploaded photographs)
```

The browser calls the API directly; Netlify does not proxy it. That is why CORS (13.4) and
the front ends' `NEXT_PUBLIC_API_BASE_URL` (13.2) both have to be right.

### 13.1 Order of work

1. Backend host: PostgreSQL, then (optionally) Key Value, then the web service (13.3).
2. First start applies the migrations (13.3). **A production migration needs the
   operating owner's sign-off, and a backup first** (`RELEASE.md`).
3. Smoke-test the API with `curl` (13.6).
4. Set `NEXT_PUBLIC_API_BASE_URL` on the three Netlify sites and redeploy them (13.2).
5. Create the first administrator from a shell on the backend (13.7).

### 13.2 Front ends on Netlify

One Netlify project per app, each linked to the GitHub repository, production branch
`main`. GitHub Actions does not deploy anything: a site builds only when its own Netlify
project is linked to the repository.

| Netlify project | Address | Base directory |
|---|---|---|
| `raksha-control-centre` | `https://raksha-control-centre.netlify.app` | `apps/control-center` |
| `raksha-citizen` | `https://raksha-citizen.netlify.app` | `apps/citizen-web` |
| `raksha-responder` | `https://raksha-responder.netlify.app` | `apps/responder-web` |

Each folder's `netlify.toml` sets the build command (`npm run build`), publish directory
(`.next`) and Node 22; the three files are identical and each app is a Next.js 16 app with
no framework differences. When `NETLIFY` is set, `next.config.ts` skips
`output: "standalone"` (that is for the Docker image). Every page is rendered per request
(the CSP nonce, `SECURITY.md` §6), and `proxy.ts` issues the nonce.

**Linked correctly?** In each site: *Site configuration → Build & deploy → Continuous
deployment* must show this repository and branch `main`. After a push to `main` the commit
should carry a Netlify status or check, and the site's *Deploys* tab should list a build.
If the commit shows only GitHub Actions, Netlify is not building it.

| Variable (Netlify, per site) | Sites | Value |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | all three | The backend's public HTTPS origin. **Compiled into the bundle and into the CSP, so redeploy after changing it.** Until a backend exists it holds a deliberate `.invalid` placeholder; leave it rather than guess a URL. |
| `NEXT_PUBLIC_CITIZEN_APP_URL` | control centre | `https://raksha-citizen.netlify.app` |
| `NEXT_PUBLIC_MAP_TILE_URL`, `NEXT_PUBLIC_MAP_ATTRIBUTION`, `NEXT_PUBLIC_DEFAULT_MAP_*` | optional | Only to override OpenStreetMap tiles or the default map view |

Every variable the front ends read starts with `NEXT_PUBLIC_` and is therefore public. Put
no secret in any of them. If the unset API variable were ever relied on, the apps fall back to
`http://localhost:8000`, which is why the placeholder is set explicitly.

### 13.3 Backend on Render

**Web service.** Runtime Docker; Dockerfile `backend/Dockerfile`; **build context the
repository root**, because the Dockerfile copies both `backend/` and `ai/`. The image listens
on **8000** (`uvicorn app.main:app --host 0.0.0.0 --port 8000`) as a non-root user. Confirm in
the dashboard how Render learns the port (it may expect `PORT`).

**Start command and migrations.** The application does not migrate on start. Either use a
pre-deploy command `alembic upgrade head` (check that your Render plan offers one), or
override the start command exactly as `docker-compose.yml` does:

```
sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Migration `0001` runs `CREATE EXTENSION IF NOT EXISTS postgis`, so the database user must be
allowed to create it (on Render, enable it once yourself with `CREATE EXTENSION postgis;` if
the migration is refused). Run a single instance while migrating; two starting at once would
race.

**Health check.** Point the platform's check at `GET /api/v1/health` (liveness: no
dependencies, so a database blip cannot restart the API). Use `GET /api/v1/health/ready`
(database, PostGIS, schema not behind the code; `503` otherwise) for external monitoring.

**PostgreSQL.** Tested only on **PostgreSQL 16 with PostGIS 3.4** (CI, compose and the
development machine). Other versions are untested; after creating the database run
`SELECT postgis_full_version();` and compare. Use the **internal** connection string for the
service and do not expose the database publicly. The URL may be `postgres://` or
`postgresql://`: the application rewrites it to the installed psycopg 3 driver. The
spatial indexes (three GiST indexes) are created by the migrations.

**Redis (optional).** Used only for rate-limit counters. Without it each process counts on
its own and a restart resets the counts. If you add a Key Value instance, set
`RAKSHA_RATE_LIMIT_BACKEND=redis` and `RAKSHA_REDIS_URL` to its internal URL; if Redis fails the
API keeps serving and counts locally.

**Uploads.** Photographs are written to local disk (`RAKSHA_MEDIA_STORAGE_PATH`; no object
storage is implemented). Attach a persistent disk and point the path at its mount. A
disk-backed service is limited to one instance. Check that the non-root user can write to the
mount by uploading a photograph (13.6).

**Environment variables** (names only; supply values in the host's secret store):

| Variable | Production | Notes |
|---|---|---|
| `RAKSHA_ENVIRONMENT` | required | `production`. The process refuses to start with an unsafe configuration. |
| `RAKSHA_DEBUG` | required | `false` (also hides `/docs`) |
| `RAKSHA_SECRET_KEY` | required | At least 32 characters, unique. `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `RAKSHA_ENCRYPTION_KEY` | required | `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`. Keep it apart from backups; without it encrypted columns are unreadable. |
| `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL` | required | `true` |
| `RAKSHA_CORS_ORIGINS` | required | The three Netlify origins (13.4), comma-separated, `https` only |
| `RAKSHA_DATABASE_URL` | required | The database's internal connection string. Alternatively `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`. |
| `RAKSHA_CITIZEN_APP_URL`, `RAKSHA_CONTROL_CENTER_URL`, `RAKSHA_RESPONDER_APP_URL` | required | The three Netlify addresses; e-mail links use them, and they must be `https` when e-mail is on |
| `RAKSHA_MEDIA_STORAGE_PATH` | required | The disk's mount path |
| `RAKSHA_RATE_LIMIT_BACKEND`, `RAKSHA_REDIS_URL` | recommended | `redis` and the Key Value internal URL |
| `RAKSHA_METRICS_TOKEN` | optional | If unset, `/metrics` does not exist (404) |
| `RAKSHA_SMTP_*`, `RAKSHA_EMAIL_FROM` | optional | Password-recovery e-mail is sent only when `RAKSHA_SMTP_HOST` is set (§12) |
| `RAKSHA_AI_ENABLED` and `RAKSHA_AI_*` | optional | Leave off unless a provider is configured; reporting does not depend on it |
| `RAKSHA_CLAMAV_*` | optional | Without a scanner, uploads are recorded as `UNSCANNED` |

Never run `scripts/seed.sh` against the production database. The seed refuses to, and its
accounts share a published password.

### 13.4 CORS

`RAKSHA_CORS_ORIGINS` must be exactly:

```
https://raksha-control-centre.netlify.app,https://raksha-citizen.netlify.app,https://raksha-responder.netlify.app
```

The API allows credentials, so only listed origins are accepted. A production-like
environment refuses to start if the list contains `*`, an `http://` origin, or nothing. Add a
custom domain's origin here when one is attached; do not add origins "just in case".

### 13.5 Backups and recovery

Render's free PostgreSQL has no backups and expires after 30 days; use a paid database for
anything that matters. Independently of the host's own backups, the repository has
`scripts/backup.sh`, `scripts/restore.sh` and the round-trip check `scripts/verify_restore.sh`
(`infrastructure/deployment/RUNBOOK.md`). The encryption key and the backup age key are
stored separately from the backups.

### 13.6 Smoke test (after step 3, with `API` set to the backend's origin)

```
curl -fsS "$API/api/v1/health"          # {"status":"ok",...}
curl -fsS "$API/api/v1/health/ready"    # "database":"ok", "postgis":"<version>", "schema_state":"current"
curl -isS -X OPTIONS "$API/api/v1/auth/login" \
  -H "Origin: https://raksha-citizen.netlify.app" \
  -H "Access-Control-Request-Method: POST"       # allow-origin: that origin
curl -isS -X OPTIONS "$API/api/v1/auth/login" \
  -H "Origin: https://example.org" \
  -H "Access-Control-Request-Method: POST"       # 400 "Disallowed CORS origin", no allow-origin header
```

Then, with an account that exists, sign in from each Netlify site and upload one photograph
from the citizen site. Do not report a deployment as working before this has been done.

### 13.7 Creating the first administrator

A new deployment has no administrator, and only an administrator can create one through the
API, so the backend ships a command for it. It is **not an HTTP endpoint**: it is run by
someone with a shell on the deployment (`docker compose exec backend ...`, or on Render a
shell or one-off job on the service - which plans offer one is for you to confirm in the
dashboard), so there is no setup page for anyone else to find.

```
python -m app.cli.create_first_admin --email you@example.org --name "Your Full Name"
```

It asks for the password at a hidden prompt, twice. For scripted use add `--password-stdin`
and pipe the password in. The password is never accepted as an argument or an environment
variable, because both leak into process listings, shell history and job settings.

What it guarantees:

- It creates one account, with the role `SUPER_ADMIN` (the only role the API will not hand to
  an ordinary administrator, and the one that can manage other administrators).
- It runs **only while no administrator account of any kind exists**, active or not. Once one
  does, it refuses (exit status 3) and changes nothing, so it cannot be used later to mint
  more. Further administrators are created in the control centre.
- Two runs at the same moment cannot both succeed (a database lock decides).
- It refuses to run when the configuration is one that production would refuse to start with
  (`RAKSHA_DEBUG` on, placeholder secret, and so on) - fix that first.
- The account must choose a new password at first sign-in and, where
  `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL` is on, enrol two-factor authentication before it can do
  anything else. Keep the recovery codes shown at enrolment.
- The creation is written to the audit log as `user.first_admin_created` (no actor, because none
  exists yet). The password is never logged, printed or stored in the audit trail.

Exit status: `0` created; `2` bad input or an unsafe configuration; `3` refused (an administrator
or that email already exists); `4` the database could not be used (check the settings and that
`alembic upgrade head` has run).

Do this once the backend is up and migrated (13.3), and before anyone tries to sign in to the
control centre. Create a second super administrator from the control centre as soon as you can:
with only one, losing their device and recovery codes locks the organisation out
(`RUNBOOK.md`, "Someone is locked out").

### 13.8 Known gaps — resolve before relying on this deployment

1. **First administrator:** resolved by the command in 13.7. It has been run end to end against a scratch database in production mode, but not on a real host.
2. **Client addresses behind a proxy.** Rate limits and the audit log use the connecting
   address. Uvicorn starts with its default of trusting forwarded headers only from
   the loopback addresses, so behind Render's proxy every user appears to be the proxy: one shared
   rate-limit bucket (including the sign-in limit) and proxy addresses in the audit trail.
   **Do not set `--forwarded-allow-ips='*'`**: uvicorn then takes the left-most
   `X-Forwarded-For` entry, which the client controls, so limits could be dodged and the
   audit address forged. Options: trust only the proxy's documented address range, put the
   repository's nginx (`infrastructure/nginx/`) in front, or accept the shared limits for a
   throwaway demo. Undecided.
3. **Uploads need a disk and one instance** (13.3), and the non-root user's write access to
   a mounted disk is unconfirmed.
4. **Free plans are for throwaway demos only.** Per Render's documentation, free web services
   spin down after inactivity and have no persistent disk; free PostgreSQL expires after
   30 days without backups; free Key Value is in-memory and loses data on restart.
5. **`repr(Settings)` and `Settings.model_dump()` include the database password** (the
   assembled URL is a computed field). Nothing logs settings today; keep it that way until
   the field is excluded.

### 13.9 What has and has not been verified

Established in this repository: the backend and the three apps build and pass their tests
and security audit in CI and locally; each app builds with `NETLIFY=true`; a
`postgres://`/`postgresql://` URL reaches the installed driver (unit tests); the first-administrator
command works end to end against a scratch database in production mode (create, refuse a second run, forced password change, mandatory MFA enrolment, then access); the start
command, ports and environment names above are read from the code and the Dockerfile.

**Not verified** (no access from the development environment): that the Netlify projects are
linked to this repository and build; that Netlify installs the npm workspace from the
repository root when the base directory is `apps/<app>` (if it does not, the fallback is
Netlify's monorepo layout: leave *Base directory* empty and set *Package directory* to the app
folder); that Netlify's Next.js runtime serves Next 16's `proxy.ts`; Render's port, health
check, pre-deploy, shell/one-off-job and disk-ownership behaviour; the PostGIS version Render provides; any live
request between a Netlify site and a deployed backend.

Sources: Render, [supported PostgreSQL extensions](https://render.com/docs/postgresql-extensions)
and [free-tier limits](https://render.com/docs/free); Netlify, [monorepos](https://docs.netlify.com/build/configure-builds/monorepos/).

Project status: `CHECKPOINT.md` §7.
