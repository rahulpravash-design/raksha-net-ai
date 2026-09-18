# Infrastructure

| Path | Contents |
|---|---|
| `docker/` | Image notes; the Dockerfiles live beside the code they build |
| `nginx/` | Reverse-proxy configuration for a single-host deployment |
| `deployment/RUNBOOK.md` | What an on-call engineer needs at 3am |

Development orchestration is `docker-compose.yml` at the repository root.
Staging and production use managed PostgreSQL, a managed secret store and a
platform load balancer — `docs/DEPLOYMENT.md` describes the target and the
production-readiness checklist.
