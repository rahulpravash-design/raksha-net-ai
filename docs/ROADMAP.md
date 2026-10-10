# RAKSHA NET AI — Development Roadmap

> **Current phase marker: Phases 0–14 complete, except Phases 8 and 9.
> Phase 16 is code-complete; the penetration test and operating-authority
> acceptance it requires cannot be done by software and are NOT done.**
> **Next: Phase 17 (Performance). Phase 15 is deliberately skipped.
> See `CHECKPOINT.md` for the exact resume point.**
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

## Phase 7 — Priority Engine (production hardening) ✅ COMPLETE

*A deterministic engine already ships in V1.* This phase makes its
configuration operational: externalised weights, versioned configuration,
agreement metrics against dispatcher decisions, and an override analytics view.

**What shipped.** `PriorityWeights` is an immutable, versioned configuration
value. The engine stays pure — it receives a configuration, it never reads
one. `app/services/priority/config_loader.py` registers an operator-supplied
JSON file named by `RAKSHA_PRIORITY_WEIGHTS_PATH`, and
`RAKSHA_PRIORITY_WEIGHTS_VERSION` pins or rolls back which registered
configuration is active — neither needs a code deploy. A malformed file stops
startup rather than silently leaving the wrong configuration in effect.

Every incident records `priority_engine_version`, and
`GET /incidents/stats/priority-agreement` reads history back through the
thresholds of whichever configuration produced each score, so re-tuning never
makes a past decision unreadable. It reports the override rate and the
(engine said, human said) matrix.

**Done when:** weights can be tuned without a code deploy, every score records
the configuration version that produced it, and override rates are
measurable. ✅

---

## Phase 8 — Computer Vision ⬜ NOT STARTED

Observations from report photographs, with a fixed label vocabulary, confidence
values and EXIF stripping. Observations are never rendered as facts.

**Planned approach (decided, not built).** A rule-based colour-histogram
heuristic over incident photos, folded into the existing analysis pipeline
through a `CompositeAnalyzer`, on the same honesty terms as the Phase 6 text
analyzer. The AI contract already carries what this needs:
`AnalysisRequest.image_bytes` and `AnalysisResult.observations` exist and are
validated, and `OBSERVATION_VOCABULARY` is already phrased as observations.

**This phase cannot be marked complete as specified.** Its completion
criterion is per-label evaluation metrics, and those require a labelled photo
dataset that does not exist. A heuristic can ship; the metrics cannot be
fabricated. Expect to mark it PARTIAL and say so.

**Done when:** evaluation metrics are published per label and the UI marks every
observation as AI-derived.

---

## Phase 9 — Voice & Multilingual Reporting ⬜ NOT STARTED

Audio upload, transcription with language hints (English, Tamil, code-mixed),
then the Phase 6 pipeline. Word error rate is measured per language before the
feature is offered; an unreliable transcript is worse than none.

**Planned approach (decided, not built).** Audio *upload* is buildable now:
extend the media validator's MIME allow-list and magic-byte table to cover
audio, which the `MediaType.AUDIO` enum already anticipates. Transcription is
not: there is no honest rule-based substitute for ASR the way there is for
keyword extraction, and no provider is configured. Plan is a `Transcriber`
protocol with a `NullTranscriber` — the same shape as `NullAnalyzer` and
`NullNotifier` — so the absence is explicit rather than pretended.

---

## Phase 10 — Resource Coordination ✅ COMPLETE

Resource inventory (ambulances, fire units, rescue teams, boats, shelters),
status lifecycle, capability matching, indexed nearest-resource search, ranked
recommendations. Recommendations only — no dispatch in this phase.

**What shipped.** `resources` carries a PostGIS location kept in sync exactly
as an incident's is, so "nearest available unit" is one index-assisted
`ST_DWithin` query. Recommendations rank suitability before proximity — a
closer unit that cannot do the job is not the better suggestion — and return
the reasons behind each ranking. The response has no dispatch field at all.
A responder may set the status of a unit they operate; anyone else's unit
reads as absent.

**Done when:** a dispatcher can see, ranked and explained, which units could
take an incident — and cannot send one from this API. ✅

---

## Phase 11 — Dispatch & Responder Application ✅ COMPLETE

Human-approved dispatch, assignment lifecycle, the responder web application,
routing and ETA. **Human approval is mandatory and is enforced by the schema:
`dispatches.approved_by_id` is `NOT NULL`.**

**What shipped.** The approver is taken from the authenticated dispatcher,
never from the request body — there is no field a client could populate to
make an unapproved dispatch look approved, and a test asserts the database
itself rejects the row. A dispatch walks a validated lifecycle, and the unit's
availability follows what its crew reports. Cancelling requires a reason.

`apps/responder-web` is a third Next.js app: a crew's own assignments, the
scene brief, a maps link, and only the progress buttons that are legal from
where they are. The brief omits the reporter's identity.

**ETA is a straight-line estimate, not routing** — it ignores roads, traffic
and terrain, and every figure the API returns is labelled as such. Real
routing (OSRM or similar) remains unbuilt.

**Done when:** a dispatcher can commit a unit, the crew can work it to
completion from their own device, and no dispatch exists without a named human
approver. ✅

---

## Phase 12 — Hospital Coordination ✅ COMPLETE

Capacity reporting, inbound-patient notice, and strict data minimisation — a
hospital receives clinical and ETA information, not the reporter's identity.

**What shipped.** Hospitals carry live bed and ICU counts maintained by their
own operator, and the nearest-facility search treats "has a free bed" as part
of the filter rather than a detail the dispatcher must notice afterwards.

Data minimisation is enforced by the shape of the record, not by convention:
`inbound_patient_notices` has no column for the reporter, their contact
details, the report text or its coordinates. A test asserts the response
carries none of them.

**Done when:** a hospital can be told what is coming without learning who
called it in. ✅

---

## Phase 13 — Notifications ⚠️ PARTIAL — in-app complete, external channels stubbed

In-app, push, SMS and email, with templates, delivery tracking, retries and
per-channel opt-out. Emergency-critical channels are never silently dropped.

**What shipped.** The in-app inbox is complete and real: notifications on
incident status change and on dispatch assignment/stand-down, scoped strictly
to their recipient, with unread counts and read marking. Delivery is recorded
per channel.

**What is stubbed.** SMS, email and push go through a `Notifier` protocol
whose only implementation is `NullNotifier`. An attempted SMS is stored as
`UNAVAILABLE` with the reason — the "never silently dropped" requirement is
met — but nothing is actually transmitted. Wiring a real provider means
returning it from `get_notifier()`; nothing else changes.

**Not built:** retries, and per-channel opt-out preferences.

**Done when:** every channel has a real provider, retries are exercised, and a
recipient can opt out per channel. ⬜

---

## Phase 14 — Analytics ✅ COMPLETE

**What shipped.** Five read-only endpoints under `/api/v1/analytics`,
restricted to dispatch-capable roles (`DISPATCHER`, `ADMIN`, `SUPER_ADMIN`) —
a hospital operator or a single responder does not need the strategic
picture: response-time (report to first dispatch) and resolution-time
(report to resolved) statistics with sample size, mean, median, min and max;
a category breakdown with counts and average priority score; resource
utilisation by type (active count, currently available, dispatches in the
window); and hotspot detection.

The hotspot endpoint is the one place this phase touches a coordinate, and it
is built to the letter of `CLAUDE.md` section 5: incident coordinates are
snapped to a ~0.01°  (~1.1 km) grid entirely in PostgreSQL `numeric` (exact
decimal) space before the query returns, so the response never carries a
reported incident's actual latitude or longitude — only a rounded cell centre
and how many incidents fell inside it. A test asserts this directly: two
incidents reported at different points inside the same cell resolve to one
hotspot whose coordinates equal neither report's own position.

All five endpoints accept `since`/`until`/`category` filters where relevant.
No migration was needed — every query reads existing tables.

---

## Phase 15 — Prediction ⬜ NOT STARTED — and deliberately so

Risk estimation from historical patterns, weather and geography. Presented as
an estimate with an uncertainty band, never as a forecast of a specific event.
Not started before a real historical dataset exists.

**Decision: skip until the precondition is met.** No real historical dataset
exists, so anything built here would be a model trained on synthetic seed data
presented as risk estimation for actual emergencies. This phase stays unbuilt
on purpose, not for lack of time.

---

## Phase 16 — Security Hardening ⚠️ CODE COMPLETE — pen test and acceptance NOT done

MFA for operational roles, upload antivirus scanning, column-level encryption of
contact details, account lockout, full security headers and CSP, dependency
audit gating, penetration test and remediation.

**This phase gates any real-world pilot.** It is not finished until the last two
items below are done by people.

**What shipped** (details and limits in `docs/SECURITY.md`):

- **Account lockout** with progressive backoff (5 failures, then 15 min,
  doubling, capped at 24 h), audited, clearable by an administrator.
- **TOTP MFA**: enrol/enable/disable, replay protection, wrong codes counted
  toward lockout, optional enforcement for every non-citizen role
  (`RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL`, required in production-like
  environments), administrator MFA reset that also revokes sessions, and a code
  field on all three sign-in pages. Verified in a real browser against the
  running stack, with an independently implemented TOTP.
- **Column-level encryption** of the three `contact_phone` columns and the MFA
  secret (Fernet, dedicated rotatable `RAKSHA_ENCRYPTION_KEY`). The migration
  encrypts existing rows and reverses cleanly.
- **Security headers and CSP** on the API and on all three Next.js apps.
- **Malware scanning** of uploads behind a `Scanner` interface (ClamAV client +
  honest `UNSCANNED` when absent).
- **Dependency-audit gating** (pip-audit, npm audit) in CI and the local gate.
  Its first run found real advisories (PyJWT, Next.js including a critical),
  which were fixed.

**Not done:**

- **Penetration test and remediation.** A human, independent act. No pen test
  has been performed; do not treat this phase as complete because the code
  exists.
- **Acceptance of residual risk by an operating authority.**
- MFA enrolment UI and recovery codes.
- Front-end CSP without `'unsafe-inline'` (needs per-request nonces).
- The ClamAV client has not been run against a real ClamAV.
- Dev-tooling advisories (`braces`, in the ESLint chain) are reported, not gating.

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
