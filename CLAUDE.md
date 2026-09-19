# RAKSHA NET AI — Project Instructions

> This file is the development constitution for this repository.
> Read it before implementing anything. If a request conflicts with this file,
> raise the conflict rather than silently deviating.

---

## 1. Product

RAKSHA NET AI is an **AI-assisted emergency response and resource coordination
platform**.

Citizens report emergencies using text, location, photographs and (later) voice.
The platform stores those reports, helps authorised operators understand and
prioritise them, and coordinates the resources that respond.

**RAKSHA NET AI is decision support. It is not an autonomous emergency
commander.** Every operational decision — priority confirmation, dispatch,
resource reassignment, incident closure — is taken by an authorised human.

Internal architecture codename: **RAKSHA CORE**.

---

## 2. Non-negotiable safety rules

1. AI **never** dispatches a resource. AI proposes; a human dispatcher disposes.
2. AI output is always labelled as AI-derived and is stored separately from
   human-verified facts (`incident_analyses` vs `incidents`).
3. Every AI output records `model_name`, `model_version` and a confidence value.
4. An AI observation is an *observation*, never a fact:
   "possible injured person detected", not "injured person present".
5. Operational priority is computed by the deterministic **Priority Engine**,
   not by an LLM. The LLM extracts structured information; the engine scores it.
6. Priority scores must be explainable: every score carries the factors that
   produced it.
7. If an AI service is unavailable, the platform must still accept reports and
   let humans triage them. AI is never on the critical path for reporting.

---

## 3. Technology

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| Maps | Leaflet + OpenStreetMap tiles |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL 16 + PostGIS 3 |
| Cache / queue | Redis |
| AI (later) | Python, scikit-learn, Transformers, LLM API |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions |
| Backend tests | pytest |
| Frontend tests | vitest |
| Quality | ruff, black, mypy (backend); eslint, prettier, tsc (frontend) |

Do not add a dependency without a written justification in the PR description.

---

## 4. Architecture rules

1. Frontend and backend are separate deployables communicating over a versioned
   HTTP API (`/api/v1`).
2. The backend is a **modular monolith**. Do not split into microservices
   without a documented scaling reason.
3. Layering is strict and one-directional:
   `api -> services -> repositories -> models`.
   - `api/` handles HTTP, auth wiring and schema translation. No business rules.
   - `services/` holds business rules. No SQLAlchemy query construction.
   - `repositories/` holds persistence. No business rules, no HTTP types.
   - `models/` are SQLAlchemy ORM entities only.
4. Request and response bodies are Pydantic schemas in `schemas/`. ORM models
   are never returned directly from an endpoint.
5. AI lives in `ai/` behind a narrow interface. Core business logic must compile,
   run and pass tests with AI entirely absent.
6. The priority engine is pure and independently testable: inputs in, score out,
   no I/O.
7. Geospatial *business logic* (distance, nearest-resource selection) lives in
   the backend. The frontend only *visualises*.
8. All configuration comes from environment variables via `app.core.config`.
   Never read `os.environ` directly outside that module.
9. Database changes require an Alembic migration. Never rely on
   `create_all()` outside tests.
10. Every state change on an incident is recorded in `incident_status_history`.
11. Sensitive actions are recorded in `audit_logs`.

---

## 5. Security rules

- Passwords are hashed with bcrypt. Never log or return a password or hash.
- JWT access tokens are short-lived; refresh tokens are opaque, hashed at rest,
  rotated on use, and revocable.
- Every endpoint declares its authorisation requirement explicitly. There is no
  "open by default" endpoint other than health and auth entry points.
- Authorisation is role-based **and** ownership-based: a citizen may read only
  their own incidents.
- All external input is validated by Pydantic before reaching a service.
- Uploads: validate declared MIME, sniff magic bytes, enforce a size cap, and
  store under a generated name — never the client-supplied filename.
- Precise citizen location is available to operational roles only; analytics
  surfaces aggregated or coarsened location.
- Secrets come from the environment or a secret manager. Never from source.
- Rate-limit authentication and reporting endpoints.

---

## 6. Code quality

Prefer: small functions, explicit types, clear names, early returns, structured
logging, narrow exceptions, dependency injection via FastAPI `Depends`.

Avoid: duplicated logic, god modules, hardcoded configuration, bare `except`,
silent failure, speculative abstraction, giant React components.

Backend must pass `ruff check`, `black --check`, `mypy app` and `pytest`.
Frontend must pass `eslint`, `tsc --noEmit`, `vitest run` and `next build`.

---

## 7. Testing requirements

A feature is not done without tests. Minimum bar per feature:

- Unit tests for business rules (services, priority engine, validators).
- Integration tests for every new endpoint: happy path, validation failure,
  unauthenticated, and **wrong-role / wrong-owner** cases.
- A migration that is applied and rolled back at least once locally.

See `docs/TESTING.md` for the full strategy and the quality gate.

---

## 8. Git conventions

Conventional commits, scoped, small:

```
feat(auth): add refresh token rotation
feat(incident): add citizen incident reporting endpoint
fix(gis): correct nearest-resource ordering for equal distances
docs(api): document incident status transitions
test(priority): add boundary cases for severity weighting
chore(ci): add mypy to the backend workflow
```

Branches: `feature/<area>-<slug>`, `fix/<area>-<slug>`.
Do not commit generated artefacts, `.env` files, or `node_modules`.

---

## 9. Development workflow

For any non-trivial change:

1. **Inspect** the existing code and docs. Do not guess.
2. **Plan**: files to add/change, schema changes, endpoints, tests, risks.
3. **Implement** the smallest complete version. Do not touch unrelated modules.
4. **Test**: run backend and frontend checks.
5. **Review** your own diff for security, authorisation and error handling.
6. **Document**: update the affected file in `docs/`.
7. **Commit** in small logical units.

---

## 10. Current development phase

**Phases 0–14 are implemented, except Phases 8 and 9.**

Built: the V1 foundation (0–5), the AI emergency analyzer (6), the versioned
priority-engine configuration (7), resource coordination (10), human-approved
dispatch with the responder application (11), hospital coordination (12),
in-app notifications (13, with external channels stubbed), and analytics (14,
response/resolution time, category and resource breakdowns, and hotspot
detection on coarsened coordinates only).

**Read `CHECKPOINT.md` before resuming.** It records the exact next step, what
is deliberately unbuilt, and how to bring the stack up.

See `docs/ROADMAP.md` for the phase definitions and completion criteria. The
current phase marker is maintained at the top of that file.

Do not implement a future phase unless explicitly asked. Not implemented:
computer vision (8), voice transcription (9), prediction (15, deliberately —
no real historical dataset exists), security hardening (16), performance
work (17) and production readiness (18).

Three things are stubbed behind an interface rather than missing, and each
reports its own absence rather than pretending: `NullAnalyzer` (AI, when
`RAKSHA_AI_ENABLED` is false) and `NullNotifier` (SMS/email/push). When you
add a real implementation, it goes behind the same interface and nothing
outside that module changes.
