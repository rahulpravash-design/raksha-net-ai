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
| Health probes wired | Liveness + readiness (DB, PostGIS, schema state); container health check | Wiring in the orchestrator |
| Log shipping, metrics, alerting | Structured logs; `/metrics`; alert suggestions in the runbook | A collector, dashboards, alert rules, paging |
| Backups running; restore rehearsed | Scripts + `verify_restore.sh`, rehearsed locally | A schedule, off-site storage, key custody; a rehearsal in the real environment |
| Penetration test, findings closed | — | **A person.** Not done |
| AI evaluation thresholds | n/a (rule-based baseline) | If a trained model is ever enabled |
| Incident-response runbook signed off | `RUNBOOK.md` (technical) | Sign-off by the responsible people |
| Release pipeline with rollback | CI; `RELEASE.md` (manual procedure) | A deploy pipeline; a rehearsal |
| **Operating authority has accepted the residual risk** | — | **A person. Not done** |

The last row is not ceremonial. This platform must not carry real emergency traffic
until a responsible authority has accepted it.
