# RAKSHA NET AI — Testing Strategy

---

## 1. Shape of the suite

```
        ╱╲          E2E (few)            citizen report -> dispatcher triage
       ╱──╲
      ╱────╲        Integration          API + database + auth, real Postgres
     ╱──────╲
    ╱────────╲      Unit (many)          priority engine, validators, services
```

Slow, brittle tests at the top; fast deterministic tests at the bottom. Business
rules are tested at the unit level so that failures point at a function, not a
stack.

## 2. Backend

**Framework:** pytest · **Location:** `backend/tests/`

```
backend/tests/
├── conftest.py          # engine, schema-per-session, session/client fixtures
├── factories.py         # user/incident builders
├── unit/                # pure logic — no database
│   ├── test_priority_engine.py
│   ├── test_geo_utils.py
│   ├── test_security.py
│   └── test_status_machine.py
└── integration/         # real PostgreSQL + PostGIS
    ├── test_health.py
    ├── test_auth_api.py
    ├── test_incidents_api.py
    ├── test_authorization.py
    ├── test_media_api.py
    └── test_geo_api.py
```

### Database strategy

Integration tests run against a **real PostgreSQL + PostGIS** instance
(`RAKSHA_TEST_DATABASE_URL`). SQLite is not substituted: it has no `geography`
type, no `ST_DWithin`, and different enum, constraint and transaction
behaviour. A suite that passes on SQLite proves nothing about the queries this
system actually runs.

Isolation: the schema is created once per session; each test runs in a
transaction that is rolled back afterwards.

### Required cases per endpoint

Every endpoint test must cover, at minimum:

1. Happy path.
2. Validation failure (`422`/`400`).
3. Unauthenticated (`401`).
4. **Wrong role** (`403`).
5. **Wrong owner** (`404` — not `403`, so existence is not confirmed).

A pull request adding an endpoint without cases 4 and 5 does not pass review.

## 3. Priority engine

The engine is pure, so it is tested exhaustively rather than sampled:

- Each factor in isolation.
- Band boundary values (just below / at / just above each threshold).
- Monotonicity: adding an aggravating fact never lowers the score.
- Determinism: identical input yields identical output, including the factor
  list and its order.
- Clamping: the score always lands in `[0, 100]`.
- Explanation completeness: every non-zero contribution appears in `factors`.

## 4. Frontend

**Framework:** vitest + Testing Library · **Location:** `apps/*/tests/`

- Unit tests for pure helpers (formatting, priority styling, API error mapping).
- Component tests for the report form: validation, geolocation denial,
  submission failure.
- Type checking (`tsc --noEmit`) and linting are part of the gate.
- Leaflet map internals are not unit-tested; they are covered by E2E.

## 5. End-to-end (Phase 5+)

Playwright, against `docker compose` with a seeded database. The one flow that
must always pass:

```
citizen registers -> logs in -> submits a report with coordinates
  -> dispatcher logs in -> sees it in the queue and on the map
  -> transitions it to UNDER_REVIEW -> citizen sees the new status
```

## 6. AI evaluation (Phase 6+)

Distinct from testing: a model is *evaluated*, not asserted. See
`AI_ARCHITECTURE.md` §9. CI runs evaluation on a fixed dataset and fails the
build on a regression in **missed-critical rate**, independently of aggregate
accuracy.

## 7. Security testing

| Test | Frequency |
|---|---|
| Authorisation matrix (role x endpoint) | Every CI run |
| Upload abuse: oversize, wrong MIME, MIME/magic mismatch, traversal filename | Every CI run |
| Rate-limit enforcement | Every CI run |
| `pip-audit` / `npm audit` | Every CI run |
| Dependency review | Weekly |
| Penetration test | Before any pilot |

## 8. Performance testing (Phase 17)

Locust scenarios for report submission and queue loading, asserted against the
NFR targets in `PRD.md` §8, with a seeded dataset of 100k incidents.

## 9. Quality gate

A change merges only when all of the following pass:

```
backend:   ruff check . && black --check . && mypy app && pytest
frontend:  npm run lint && npm run typecheck && npm run test && npm run build
coverage:  backend services + api >= 80%
docs:      the affected file in docs/ is updated
```

CI enforces this on every pull request (`.github/workflows/ci.yml`).

## 10. Commands

```bash
# Backend
cd backend
pytest                                  # everything
pytest tests/unit -q                    # fast, no database
pytest --cov=app --cov-report=term-missing
ruff check . && black --check . && mypy app

# Frontend
cd apps/citizen-web
npm run lint && npm run typecheck && npm run test && npm run build

# Everything, from the repository root
make check
```
