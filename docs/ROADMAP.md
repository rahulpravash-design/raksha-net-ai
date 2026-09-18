# RAKSHA NET AI — Development Roadmap

> **Current phase marker: Phases 0–6 complete. Next: Phase 7.**
>
> Do not implement a future phase unless explicitly requested.

Each phase lists its objective, scope, dependencies, tests and completion
criteria. A phase is complete only when every criterion is demonstrably met —
not when the code exists.

---

## Phase 0 — Foundation ✅ COMPLETE

**Objective.** A reproducible, documented, testable development environment.

Scope: repository structure; `CLAUDE.md`; the eleven specification documents;
Docker Compose for PostgreSQL/PostGIS and Redis; FastAPI skeleton with config,
structured logging, error handling and health endpoints; Next.js skeletons;
Alembic; pytest and vitest harnesses; GitHub Actions CI; `README`.

Tests: backend starts; health and readiness pass; database connects; PostGIS
present; frontends build; lint, type check and tests run clean.

**Done when:** `docker compose up` brings the stack up, `GET /api/v1/health/ready`
returns `ok`, `make check` passes, and no secret is committed.

---

## Phase 1 — Authentication & Identity ✅ COMPLETE

**Objective.** Trustworthy identity and role-based authorisation.

Scope: `users` and `refresh_tokens`; bcrypt hashing; registration; login;
rotating refresh tokens with reuse detection; logout; `/auth/me`; role
dependencies; admin user management; audit entries for authentication events.

Depends on: Phase 0.

Tests: registration validation and duplicate rejection; login success and
failure; uniform failure responses; token expiry; refresh rotation; reuse
detection revoking the chain; the full role × endpoint authorisation matrix.

**Done when:** every endpoint declares its authorisation, the matrix is covered
by tests, and no password or token material appears in any log or response.

---

## Phase 2 — Citizen Emergency Reporting ✅ COMPLETE

**Objective.** A citizen can report an emergency and track it.

Scope: `incidents` and `incident_media`; report creation with validated
coordinates; media upload with size, MIME and magic-byte validation; own-reports
list and detail; reference codes; the citizen web application.

Depends on: Phase 1.

Tests: creation happy path; coordinate rejection (range, bbox, null island);
description bounds; oversize upload; disallowed MIME; MIME/magic mismatch;
path-traversal filename; one citizen cannot read another's incident.

**Done when:** a citizen can submit a report with a photo from a browser and see
it listed with its reference code and status.

---

## Phase 3 — Incident Management ✅ COMPLETE

**Objective.** A governed incident lifecycle with a complete audit trail.

Scope: the status state machine; `incident_status_history`; dispatcher fact
updates; assignment; cancellation by the reporter; `audit_logs`; queue filtering,
search, sorting and pagination; summary statistics.

Depends on: Phase 2.

Tests: every legal transition; rejection of every illegal transition; history
written on each change; citizen may cancel only before assignment; audit entries
present for every sensitive action.

**Done when:** an incident can be driven from `REPORTED` to `CLOSED` with every
step recorded, and no illegal transition is reachable through the API.

---

## Phase 4 — GIS & Location ✅ COMPLETE

**Objective.** Correct, indexed spatial queries.

Scope: `geography(Point,4326)` with a `GIST` index; latitude/longitude kept in
sync on write; radius search via `ST_DWithin`; bounding-box search returning
GeoJSON; distance in kilometres; the configurable operating bounding box.

Depends on: Phase 2.

Tests: distance accuracy against known coordinate pairs; radius inclusion and
exclusion at the boundary; bbox filtering; radius cap enforcement; GeoJSON
shape; index used (verified by `EXPLAIN` in review).

**Done when:** "incidents within N km of a point" returns correct, ordered,
index-assisted results.

---

## Phase 5 — Control Centre ✅ COMPLETE

**Objective.** A dispatcher can triage the full incident picture.

Scope: operator login; dashboard counts by band and status; prioritised queue
with filters; incident detail with media, history and the priority explanation;
live Leaflet map with priority-coded markers; status transitions and priority
override from the UI.

Depends on: Phases 3 and 4.

Tests: queue ordering; filter correctness; map data endpoint; transition and
override from the UI; component tests for the queue and detail views.

**Done when:** the end-to-end flow works: citizen reports → dispatcher sees it in
the queue and on the map → dispatcher changes status → citizen sees the change.

---

## Phase 6 — AI Emergency Analyzer ✅ COMPLETE

**Objective.** Structured information extracted from report text, as a proposal.

Scope: `incident_analyses`; the `EmergencyAnalyzer` interface with a real text
implementation; classification, entity extraction and severity proposal; strict
output validation; the dispatcher review UI (accept / edit / reject).

Depends on: Phase 5.

**What shipped.** `ai/nlp/text_analyzer.py`'s `HeuristicTextAnalyzer` is the V2
implementation behind `get_analyzer(enabled=True)`: keyword and regex
extraction over the report's own description, with confidence deliberately
capped below certainty (`docs/AI_ARCHITECTURE.md` section 7's "a simple
baseline ships first"). A trained classifier is deferred, honestly, until the
labelled dataset this phase originally called for exists — shipping an
unevaluated model would be worse than shipping a transparent heuristic.
Swapping it in later changes nothing outside `ai/`.

`incident_analyses` stores every proposal, kept apart from `incidents`
(CLAUDE.md section 2, rule 2). Accepting or editing a proposal is never a
direct write: it is built into an `IncidentUpdate` and passed to
`IncidentService.update_facts`, the same audited, priority-recalculating path
a dispatcher's manual correction takes. A rejected or unreviewed proposal
never touches the incident.

Tests: the validator rejects malformed, out-of-range and unknown-field output
(`ai/tests`); a disabled or failing analyzer never blocks reporting; AI output
never writes to `incidents.priority_*`; every proposal, acceptance, edit and
rejection is audited (`backend/tests/integration/test_analyses_api.py`); the
control-centre review panel is covered for the accept, edit and reject paths
and for the non-dispatch read-only view (`apps/control-center/tests`).

**Done when:** a dispatcher sees an AI proposal beside the citizen's own words
and must act for anything to change. ✅

---

## Phase 7 — Priority Engine (production hardening) ⬜ NOT STARTED

*A deterministic engine already ships in V1.* This phase makes its
configuration operational: externalised weights, versioned configuration,
agreement metrics against dispatcher decisions, and an override analytics view.

**Done when:** weights can be tuned without a code deploy, every score records
the configuration version that produced it, and override rates are measurable.

---

## Phase 8 — Computer Vision ⬜ NOT STARTED

Observations from report photographs, with a fixed label vocabulary, confidence
values and EXIF stripping. Observations are never rendered as facts.

**Done when:** evaluation metrics are published per label and the UI marks every
observation as AI-derived.

---

## Phase 9 — Voice & Multilingual Reporting ⬜ NOT STARTED

Audio upload, transcription with language hints (English, Tamil, code-mixed),
then the Phase 6 pipeline. Word error rate is measured per language before the
feature is offered; an unreliable transcript is worse than none.

---

## Phase 10 — Resource Coordination ⬜ NOT STARTED

Resource inventory (ambulances, fire units, rescue teams, hospitals, shelters),
status lifecycle, capability matching, KNN nearest-resource search, ranked
recommendations. Recommendations only — no dispatch in this phase.

---

## Phase 11 — Dispatch & Responder Application ⬜ NOT STARTED

Human-approved dispatch, assignment lifecycle, the responder web application,
routing and ETA. **Human approval is mandatory and is enforced by the schema:
`dispatches.approved_by_id` is `NOT NULL`.**

---

## Phase 12 — Hospital Coordination ⬜ NOT STARTED

Capacity reporting, inbound-patient notice, and strict data minimisation — a
hospital receives clinical and ETA information, not the reporter's identity.

---

## Phase 13 — Notifications ⬜ NOT STARTED

In-app, push, SMS and email, with templates, delivery tracking, retries and
per-channel opt-out. Emergency-critical channels are never silently dropped.

---

## Phase 14 — Analytics ⬜ NOT STARTED

Response-time and resolution metrics, category breakdowns, resource
utilisation, and hotspot detection on **coarsened** coordinates.

---

## Phase 15 — Prediction ⬜ NOT STARTED

Risk estimation from historical patterns, weather and geography. Presented as
an estimate with an uncertainty band, never as a forecast of a specific event.
Not started before a real historical dataset exists.

---

## Phase 16 — Security Hardening ⬜ NOT STARTED

MFA for operational roles, upload antivirus scanning, column-level encryption of
contact details, account lockout, full security headers and CSP, dependency
audit gating, penetration test and remediation.

**This phase gates any real-world pilot.**

---

## Phase 17 — Performance & Scalability ⬜ NOT STARTED

Load testing against the NFR targets, query tuning, caching, partitioning,
connection-pool tuning, read replicas.

---

## Phase 18 — Production Readiness ⬜ NOT STARTED

Managed infrastructure, secret management, observability, backup and rehearsed
restore, release pipeline with rollback, runbooks, and formal acceptance by an
operating authority.

---

## Version map

| Version | Phases | Meaning |
|---|---|---|
| V1 | 0–5 | Report → triage → map → status, end to end |
| V2 | 6–7 | AI analysis and an operational priority engine |
| V3 | 8–9 | Multimodal reporting |
| V4 | 10–11 | Resource coordination and dispatch |
| V5 | 12–13 | Hospital coordination and notifications |
| V6 | 14–15 | Analytics and prediction |
| V7 | 16–18 | Production readiness |
