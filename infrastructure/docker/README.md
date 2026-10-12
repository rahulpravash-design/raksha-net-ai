# Container images

Each Dockerfile sits beside the code it builds:

| Image | Dockerfile | Build context |
|---|---|---|
| Backend | `backend/Dockerfile` | repository root |
| Citizen web | `apps/citizen-web/Dockerfile` | repository root |
| Control centre | `apps/control-center/Dockerfile` | repository root |

All three build from the **repository root**, because the backend image also
needs `ai/` and the front-end images need the shared `packages/api-client`
workspace:

```bash
docker build -f backend/Dockerfile -t raksha/backend .
docker build -f apps/citizen-web/Dockerfile -t raksha/citizen-web .
docker build -f apps/control-center/Dockerfile -t raksha/control-center .
```

Shared properties:

- Non-root user (uid 10001) — a container escape should not start as root.
- No secrets baked in; everything comes from the environment at runtime.
- Frontend images use Next.js standalone output, so they carry only what the
  server needs.
- The backend image declares a `HEALTHCHECK` against `/api/v1/health/ready`.
