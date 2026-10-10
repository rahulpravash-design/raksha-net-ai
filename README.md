# RAKSHA NET AI

**AI-assisted emergency response and resource coordination.**

Citizens report emergencies with text, location and photographs. The platform
turns each report into structured, geolocated, auditable data, scores it with a
deterministic and explainable priority engine, and gives authorised operators a
live map and queue to triage from.

> **AI is decision support, not autonomous emergency command.**
> Structured information may be extracted automatically, but operational
> priority is computed by a deterministic engine and every dispatch decision is
> taken by a trained human operator. See `docs/AI_ARCHITECTURE.md`.

---

## Status

| Version | Phases | State |
|---|---|---|
| **V1 — Foundation** | 0–5 | **Implemented.** Report → triage → map → status, end to end |
| V2 — AI analysis | 6–7 | **Implemented.** Rule-based text analyzer with a dispatcher review workflow; versioned priority-engine configuration |
| V3 — Multimodal | 8–9 | Specified, not implemented. Vision and voice both need an input this deployment does not have — see `docs/ROADMAP.md` |
| V4 — Resources & dispatch | 10–11 | **Implemented.** Resource inventory with ranked recommendations, human-approved dispatch, and the responder application |
| V5 — Hospitals & notifications | 12–13 | Phase 12 **implemented**. Phase 13 in-app only for incidents; SMS and push are stubbed. Email is real when an SMTP host is configured, and carries account recovery only |
| V6 — Analytics | 14 | **Implemented.** Response/resolution time, category and resource breakdowns, hotspots on coarsened coordinates |
| V7 | 15–18 | Phase 15 skipped deliberately. **16 code-complete** (lockout, MFA, encryption, CSP, scanning, audit gating) — its penetration test and risk acceptance are **not** done. **17 measured and fixed in a dev environment only** (targets met with margin; an overload deadlock found and fixed; no production capacity evidence). **18 artifacts built, nothing deployed**: `/metrics`, verified backup/restore, schema-aware readiness, release procedure |

`docs/ROADMAP.md` holds the phase definitions and completion criteria.

**This platform must not carry real emergency traffic.** Phase 16's code is in,
but no penetration test has been performed and no operating authority has
accepted the residual risk. See `docs/SECURITY.md` §12.

## What V1 does

- Citizen registration and login, with rotating refresh tokens and replay
  detection.
- Emergency reporting: category, description, validated GPS coordinates,
  people-affected facts and photograph upload.
- A deterministic priority engine that scores 0–100 and records **every factor
  that produced the score**, so a dispatcher can audit the number.
- A governed incident lifecycle: twelve statuses, a validated transition table,
  and an append-only history of every change with its actor.
- PostGIS spatial queries: incidents within a radius, and a GeoJSON viewport
  feed for the map.
- A control centre (dark, with a 3D globe landing page and Map ⇄ Globe views — `docs/FRONTEND.md`) with priority counts, a filterable queue, a live Leaflet map
  and an incident console for status changes and priority override.
- An append-only audit log of every sensitive action.

## What V2 (Phase 6) adds

- An AI analyzer (`ai/nlp/text_analyzer.py`) that proposes a category,
  severity, headcount and rescue signals from a report's own description —
  a transparent, rule-based baseline, honestly labelled as such rather than an
  unevaluated trained model.
- Every proposal is stored in `incident_analyses`, separate from `incidents`,
  and never changes an incident by itself.
- A control-centre review panel where a dispatcher accepts, edits or rejects
  each proposal; acceptance runs through the exact same audited,
  priority-recalculating path a manual fact correction does.
- `RAKSHA_AI_ENABLED` still defaults to `false`; the Docker Compose dev stack
  turns it on because this analyzer needs no external provider or API key.

## Architecture

```
  Citizen web            Control centre            Responder web
  (Next.js)              (Next.js + Leaflet)
       │                        │                          │
       └────────────────────────┴──────────────┬───────────┘
                                HTTPS / JSON   │  /api/v1
                                     ┌─────────▼──────────┐
                                     │  FastAPI backend   │
                                     │   (RAKSHA CORE)    │
                                     │                    │
                                     │  api → services →  │
                                     │  repositories →    │
                                     │  models            │
                                     └─────────┬──────────┘
                    ┌──────────────────┬───────┴────────┬─────────────────┐
                    ▼                  ▼                ▼                 ▼
          PostgreSQL + PostGIS      Redis         object storage      ai/ (Phase 6)
          (system of record)     (rate limit)     (media)          text analyzer,
                                                                   behind one interface
```

`docs/ARCHITECTURE.md` explains each choice and records the decisions.

## Technology

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Maps | Leaflet + OpenStreetMap |
| Backend | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 |
| Migrations | Alembic |
| Database | PostgreSQL 16 + PostGIS 3 |
| Cache | Redis |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions |

## Repository layout

```
raksha-net-ai/
├── CLAUDE.md                 Development constitution — read before changing anything
├── apps/
│   ├── citizen-web/          Reporting and status tracking
│   ├── control-center/       Operator triage, map and incident console
│   └── responder-web/        Crew assignments, scene brief and progress
├── packages/
│   └── api-client/           Typed API client shared by all three front ends
├── backend/
│   ├── app/
│   │   ├── api/              HTTP layer: routing, auth wiring, schema translation
│   │   ├── core/             Config, security, logging, errors, rate limiting
│   │   ├── models/           SQLAlchemy entities
│   │   ├── repositories/     Persistence, including every PostGIS query
│   │   ├── schemas/          Pydantic request and response contracts
│   │   ├── services/         Business rules, incl. the priority engine
│   │   └── utils/            Geo validation, reference codes, time
│   ├── migrations/           Alembic revisions
│   └── tests/                unit/ (no database) and integration/ (real PostGIS)
├── ai/                       The AI boundary. NullAnalyzer, plus a rule-based
│                             text analyzer (Phase 6).
├── database/                 Seeds and schema notes
├── docs/                     The eleven specification documents
├── infrastructure/           Deployment notes and runbooks
└── scripts/                  bootstrap, migrate, seed, dev, check
```

## Getting started

### With Docker

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and RAKSHA_SECRET_KEY
docker compose up
```

| Service | URL |
|---|---|
| Citizen app | http://localhost:3000 |
| Control centre | http://localhost:3001 |
| Responder app | http://localhost:3002 |
| API | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |

### Without Docker

Requires Python 3.11+, Node 20+, and PostgreSQL 16 with PostGIS.

```bash
./scripts/bootstrap.sh        # venv, npm install, generate a dev secret
# edit .env: set POSTGRES_PASSWORD
./scripts/migrate.sh          # apply migrations
./scripts/seed.sh --reset     # synthetic development data
./scripts/dev_backend.sh      # API on :8000
npm run dev:citizen           # citizen app on :3000
npm run dev:control           # control centre on :3001
npm run dev --workspace @raksha/responder-web   # responder app on :3002
```

### Seeded accounts

Development only. The seed script refuses to run in staging or production.

| Email | Role |
|---|---|
| `citizen@raksha.example` | CITIZEN |
| `responder@raksha.example` | RESPONDER |
| `dispatcher@raksha.example` | DISPATCHER |
| `hospital@raksha.example` | HOSPITAL_OPERATOR |
| `admin@raksha.example` | ADMIN |

Password for all of them: `raksha-development-only`

## Development commands

```bash
make help              # list every task
make check             # the full quality gate, exactly as CI runs it
make test              # every test suite
make migrate           # apply migrations
make seed              # reload synthetic data
```

Backend only:

```bash
cd backend
.venv/bin/pytest -q                                   # all tests
.venv/bin/pytest tests/unit -q                        # fast, no database
.venv/bin/ruff check . && .venv/bin/black --check .
.venv/bin/mypy app
```

Frontend only:

```bash
npm run lint --workspace @raksha/citizen-web
npm run typecheck --workspace @raksha/citizen-web
npm run test --workspace @raksha/citizen-web
npm run build --workspace @raksha/citizen-web
```

## Testing

Integration tests run against a **real PostgreSQL + PostGIS** instance. SQLite
is not substituted: it has no `geography` type and no `ST_DWithin`, so a suite
that passed on it would say nothing about the queries this system runs.

Every endpoint is covered for the happy path, validation failure,
unauthenticated access, **wrong role**, and **wrong owner**. `docs/TESTING.md`
holds the full strategy and the quality gate.

## Documentation

| Document | Contents |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Development constitution: rules, layering, conventions |
| [`docs/PRD.md`](docs/PRD.md) | Problem, users, journeys, requirements, success measures |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and the decision record |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Entities, indexes, migrations, retention |
| [`docs/API.md`](docs/API.md) | Every endpoint, error code and planned route |
| [`docs/AI_ARCHITECTURE.md`](docs/AI_ARCHITECTURE.md) | Pipeline, contracts, confidence, evaluation |
| [`docs/GIS_ARCHITECTURE.md`](docs/GIS_ARCHITECTURE.md) | Coordinates, spatial queries, routing, privacy |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model and every control |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy and the quality gate |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Environments, CI/CD, observability, backups |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Every phase, with completion criteria |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Design system, 3D layer, dependencies, what is and is not built |

## Contributing

Read `CLAUDE.md` first. In short: inspect before changing, keep the layering
one-directional, add tests including the wrong-role and wrong-owner cases,
update the affected document in `docs/`, and commit in small conventional
units.

## Licence

MIT — see [LICENSE](LICENSE).
