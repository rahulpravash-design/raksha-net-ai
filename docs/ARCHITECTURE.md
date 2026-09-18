# RAKSHA NET AI — System Architecture

Codename: **RAKSHA CORE** · Status: Baseline v1.0

---

## 1. System context

```
   ┌────────────┐   ┌────────────────┐   ┌──────────────┐   ┌────────────┐
   │  Citizen   │   │ Control Centre │   │  Responder   │   │  Hospital  │
   │    Web     │   │      Web       │   │  Web (V7)    │   │  Web (V8)  │
   └──────┬─────┘   └────────┬───────┘   └──────┬───────┘   └──────┬─────┘
          │                  │                  │                  │
          └──────────────────┴────────┬─────────┴──────────────────┘
                                      │  HTTPS / JSON  (/api/v1)
                             ┌────────▼─────────┐
                             │  FastAPI backend │
                             │  (RAKSHA CORE)   │
                             └────────┬─────────┘
             ┌───────────────┬────────┼─────────┬──────────────┐
             ▼               ▼        ▼         ▼              ▼
     PostgreSQL+PostGIS   Redis   Object     AI services   Notification
      (system of record) (cache)  storage    (Phase 6+)    providers (P13)
```

## 2. Component responsibilities

| Component | Responsibility | Explicitly not responsible for |
|---|---|---|
| `apps/citizen-web` | Reporting UX, status tracking | Priority logic, authorisation decisions |
| `apps/control-center` | Triage, map, dispatch UX | Computing priority, spatial maths |
| `backend` | API, authN/authZ, incident lifecycle, priority engine, spatial queries, audit | Model training, rendering |
| `ai` | Extraction and observation from text/image/audio | Deciding priority, dispatching |
| PostgreSQL/PostGIS | System of record, spatial index | Business rules |
| Redis | Rate limiting, cache, future queue | Durable state |

## 3. Why these technologies

- **FastAPI + Pydantic v2** — typed request/response contracts validated at the
  boundary, OpenAPI generated from the same types, and native async for the
  I/O-bound work this system does. Python also keeps the backend and the future
  AI services in one language.
- **PostgreSQL + PostGIS** — "find the nearest available ambulance within 10 km"
  is a spatial index query, not application code. PostGIS gives correct
  geodesic distance (`geography` type) and `GIST` indexes. One database for
  relational and spatial data avoids a second system of record.
- **SQLAlchemy 2 + Alembic** — explicit typed ORM and reviewable, reversible
  schema migrations.
- **Next.js + TypeScript** — App Router server components for the read-heavy
  dashboard, one language across three front ends, and a straightforward
  deployment story.
- **Leaflet + OpenStreetMap** — no per-seat licensing, works with self-hosted
  tiles for an air-gapped deployment, and integrates cleanly with GeoJSON.
- **Redis** — rate limiting and short-lived cache now; Celery broker later.
- **Modular monolith** — one deployable until measured load justifies
  splitting. AI is the one boundary drawn early, because its runtime profile
  (GPU, long latency, unreliable third parties) genuinely differs.

## 4. Backend structure

```
backend/app/
├── main.py              # app factory, middleware, router mounting, lifespan
├── api/
│   ├── deps.py          # auth/session/role dependencies
│   └── v1/
│       ├── router.py    # aggregates v1 routes
│       └── endpoints/   # health, auth, users, incidents, media, geo
├── core/
│   ├── config.py        # Settings (pydantic-settings) — the only env reader
│   ├── security.py      # hashing, JWT encode/decode
│   ├── logging.py       # structured logging + correlation id
│   ├── errors.py        # AppError hierarchy + handlers
│   └── rate_limit.py    # fixed-window limiter (memory | redis)
├── db/
│   ├── base.py          # DeclarativeBase, naming convention
│   └── session.py       # engine, sessionmaker, get_db dependency
├── models/              # SQLAlchemy ORM entities
├── schemas/             # Pydantic request/response models
├── repositories/        # persistence, all query construction
├── services/            # business rules
│   ├── auth_service.py
│   ├── incident_service.py
│   ├── media_service.py
│   └── priority/        # pure, deterministic priority engine
└── utils/               # geo helpers, reference codes, time
```

**Dependency rule.** `api -> services -> repositories -> models`.
A lower layer never imports a higher one. `schemas` may be imported anywhere;
`models` are never returned across the API boundary.

## 5. Request lifecycle

```
HTTP request
  │
  ├─ CorrelationIdMiddleware      attach/propagate X-Request-ID
  ├─ AccessLogMiddleware          structured request log with duration
  ├─ RateLimitMiddleware          fixed window per identity+route class
  ├─ CORS                         explicit origin allow-list
  │
  ├─ Route dependency graph
  │     get_db            -> scoped SQLAlchemy session
  │     get_current_user  -> decode JWT, load user, check active
  │     require_roles(..) -> role assertion
  │
  ├─ Endpoint  -> Service  -> Repository -> PostgreSQL
  │
  └─ Response: Pydantic model serialised; AppError -> RFC7807-style JSON
```

## 6. Incident lifecycle (state machine)

```
REPORTED ──► RECEIVED ──► UNDER_REVIEW ──► PRIORITIZED ──► ASSIGNED
                                                              │
                                                              ▼
                                                      RESPONDER_EN_ROUTE
                                                              │
                                                              ▼
                                                          ON_SCENE
                                                              │
                                                              ▼
                                                          RESOLVED ──► CLOSED

Terminal side-exits from any pre-RESOLVED state:
    CANCELLED   (withdrawn by reporter)
    DUPLICATE   (merged into another incident)
    REJECTED    (not an emergency / abuse)
```

Transitions are validated centrally in `services/incident_service.py` against
`ALLOWED_TRANSITIONS`. Citizens may only `CANCELLED` their own incident, and
only before it is `ASSIGNED`. Every transition writes `incident_status_history`.

## 7. Priority architecture

```
 citizen-declared facts ─┐
 operator-verified facts ─┼─► PriorityEngine (pure) ─► PriorityResult
 AI-extracted facts (V2) ─┘                            score 0..100
                                                       band CRITICAL..LOW
                                                       factors[]  (explanation)
                                                              │
                                                              ▼
                                                   dispatcher confirms / overrides
```

The engine is a pure function: no database, no clock, no network. Time-based
factors receive `now` as an argument. This makes it exhaustively testable and
lets the control centre show *why* an incident scored as it did.

AI never writes to `incidents.priority_score`. It writes to
`incident_analyses`, and a human decides what to accept.

## 8. Geospatial architecture

Coordinates are stored twice by intent:

- `latitude` / `longitude` as `NUMERIC` — the durable, human-readable value.
- `geom` as `geography(Point, 4326)` — the indexed value used for queries.

They are kept in sync by the repository layer on write. See
`GIS_ARCHITECTURE.md`.

## 9. AI boundary

The backend calls AI through one narrow interface
(`ai/common/interfaces.py: EmergencyAnalyzer`). V1 ships a
`NullAnalyzer`. Consequences of this boundary:

- The platform runs with AI disabled (`RAKSHA_AI_ENABLED=false`).
- AI failures degrade triage quality; they never block reporting.
- Swapping a model or provider touches one module.

## 10. Real-time (Phase 5+)

V1 uses polling with a short interval in the control centre — correct,
trivially cacheable and sufficient at pilot scale. A WebSocket channel
(`/api/v1/ws/incidents`) is specified in `API.md` for Phase 5 and will publish
incident-created and status-changed events fanned out through Redis pub/sub.

## 11. Deployment topology

See `DEPLOYMENT.md`. Development is `docker compose`: `postgres` (PostGIS
image), `redis`, `backend`, `citizen-web`, `control-center`.

## 12. Architecture decision record (summary)

| ID | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| ADR-01 | Modular monolith | Pilot scale; one deployable | Microservices — premature |
| ADR-02 | PostGIS over app-side maths | Correct geodesy + index | Haversine in Python |
| ADR-03 | Deterministic priority engine | Auditable, testable, safe | LLM-assigned priority |
| ADR-04 | AI writes to a separate table | Never confuse inference with fact | Overwriting incident fields |
| ADR-05 | Opaque, hashed, rotating refresh tokens | Revocable sessions | Long-lived JWT |
| ADR-06 | Polling before WebSockets | Simpler, adequate at pilot scale | WebSockets in V1 |
| ADR-07 | Local media storage behind an interface | No cloud dependency in dev | Direct S3 coupling |
