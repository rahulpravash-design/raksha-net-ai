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
| Metrics | Prometheus: request rate, latency histogram, error rate, DB pool usage, queue depth |
| Traces | OpenTelemetry (Phase 18) |
| Errors | Sentry or equivalent, with PII scrubbing |
| Uptime | External probe against `/health/ready` |

Alerts that page: readiness failing, error rate > 2% over 5 minutes, p95 report
latency > 2 s, database connection saturation, disk > 85%.

## 9. Backup and recovery

- Automated daily full backup plus continuous WAL archiving. **RPO 15 minutes,
  RTO 1 hour.**
- Restores are rehearsed quarterly into an isolated environment; a backup that
  has never been restored is not a backup.
- Media object storage uses versioning and lifecycle rules.
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

## 11. Production readiness checklist

```
[ ] Managed PostgreSQL with PostGIS, encrypted at rest
[ ] Secrets in a managed secret store
[ ] TLS terminated, HSTS enabled, security headers verified
[ ] CORS restricted to known origins
[ ] Rate limiting enabled and backed by Redis
[ ] Migrations applied and verified
[ ] Health probes wired to the orchestrator
[ ] Log shipping, metrics and alerting live
[ ] Backups running and a restore rehearsed
[ ] Penetration test completed and findings closed
[ ] AI evaluation thresholds met (if AI is enabled)
[ ] Incident-response and escalation runbook signed off
[ ] Operating authority has accepted the residual risk
```

The last item is not ceremonial. This platform must not carry real emergency
traffic until a responsible authority has accepted it.
