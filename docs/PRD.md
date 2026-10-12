# RAKSHA NET AI — Product Requirements Document

Status: **Baseline v1.0** · Owner: Product · Last reviewed: Phase 0

---

## 1. Vision

Emergency reporting today is fragmented across phone lines, messaging apps and
paper logs. Control rooms receive unstructured information, often in a language
or dialect that is hard to transcribe under stress, and must manually decide
what matters most and who to send.

RAKSHA NET AI gives citizens one channel to report an emergency, converts that
report into structured, geolocated, auditable data, and gives authorised
operators the tools to prioritise incidents and coordinate the resources that
respond.

**Positioning statement**

> RAKSHA NET AI is an AI-assisted emergency coordination system in which AI
> analyses incoming information and recommends actions, while authorised human
> operators remain responsible for every operational decision.

## 2. Problem

| # | Problem | Consequence |
|---|---|---|
| P1 | Reports arrive unstructured and in inconsistent formats | Slow triage, manual re-keying |
| P2 | Location is described in prose ("near the temple") | Responders are dispatched to the wrong place |
| P3 | Severity is judged ad hoc, differently by each operator | Inconsistent prioritisation |
| P4 | Resource availability is tracked outside the incident system | Duplicate or missed dispatch |
| P5 | There is no durable audit trail of decisions | No post-incident review, no accountability |
| P6 | Citizens have no visibility after reporting | Repeat calls, congested lines |

## 3. Users and stakeholders

| Role | Description | Primary need |
|---|---|---|
| `CITIZEN` | Any member of the public | Report fast, know it was received |
| `RESPONDER` | Ambulance crew, fire crew, rescue team member | Clear assignment, location, status updates |
| `DISPATCHER` | Control-centre operator | Prioritised queue, map, resource picture, dispatch control |
| `HOSPITAL_OPERATOR` | Hospital emergency desk | Advance warning of arrivals, capacity reporting |
| `ADMIN` | Agency administrator | User/resource management, configuration |
| `SUPER_ADMIN` | Platform operator | Full administration, audit access |

Non-user stakeholders: district emergency authority, data-protection officer,
platform SRE.

## 4. Scope by version

### V1 (implemented)

- Citizen registration, login, session management.
- Citizen emergency reporting: category, description, GPS location, photos.
- Incident lifecycle with recorded status history.
- Dispatcher control centre: prioritised queue, incident detail, live map,
  status changes, assignment notes.
- Spatial queries: incidents near a point, bounding-box map queries.
- A deterministic, explainable priority engine driven by citizen-declared and
  operator-verified facts.

### V2+ (documented, not implemented)

AI text analysis, computer vision on report photos, voice and multilingual
reporting, resource inventory and matching, responder application, hospital
coordination, notifications, analytics and risk estimation.

## 5. Core product loop

```
Citizen report  ->  Ingest & validate  ->  (AI extraction)  ->  Priority engine
      ->  Dispatcher review  ->  Assignment  ->  Response  ->  Resolution
      ->  Citizen status visibility  ->  Audit & analytics
```

## 6. Key user journeys

### J1 — Citizen reports an emergency (V1)

1. Citizen registers or logs in.
2. Selects an incident category.
3. Describes the situation in free text.
4. Shares GPS location (browser geolocation) or adjusts a map pin.
5. Declares people affected / trapped / medical need.
6. Optionally attaches photographs.
7. Submits; receives a reference number and a status page.

### J2 — Dispatcher triages the queue (V1)

1. Dispatcher logs in to the control centre.
2. Sees counts by priority and a queue ordered by priority score, then age.
3. Opens an incident: description, media, location, priority explanation.
4. Verifies or overrides the priority, recording a reason.
5. Moves the incident through its lifecycle; the citizen sees status change.

### J3 — AI-assisted triage (V2, documented)

The analyzer proposes structured fields and a confidence value. The dispatcher
sees the proposal side by side with the citizen's own words and confirms,
edits or rejects it. Nothing is dispatched on the AI's say-so.

## 7. Functional requirements (V1)

| ID | Requirement |
|---|---|
| FR-01 | A citizen can register with email and password and log in. |
| FR-02 | Passwords are hashed; a minimum length is enforced. |
| FR-03 | Sessions use short-lived access tokens and rotating refresh tokens. |
| FR-04 | A citizen can create an incident report with category, description and coordinates. |
| FR-05 | Coordinates are validated for range and a configured operating bounding box. |
| FR-06 | A citizen can attach images up to a configured size and MIME allow-list. |
| FR-07 | A citizen can list and read **only their own** incidents. |
| FR-08 | A dispatcher can list, filter and read **all** incidents. |
| FR-09 | Every incident receives a priority score with recorded contributing factors. |
| FR-10 | A dispatcher can override priority with a mandatory reason. |
| FR-11 | Status transitions are validated against the lifecycle state machine. |
| FR-12 | Every status change is recorded with actor, timestamp and note. |
| FR-13 | Incidents can be queried by radius around a point and by bounding box. |
| FR-14 | The control centre renders incidents on a map with priority-coded markers. |
| FR-15 | Sensitive actions are written to an append-only audit log. |
| FR-16 | The API exposes a health endpoint reporting database connectivity. |

## 8. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Report submission latency (p95, excl. media upload) | < 500 ms |
| NFR-02 | Control-centre queue load (p95, 500 open incidents) | < 1.5 s |
| NFR-03 | Availability of reporting path | 99.9% |
| NFR-04 | Reporting must work when AI services are down | Hard requirement |
| NFR-05 | All traffic over TLS in any deployed environment | Hard requirement |
| NFR-06 | Structured JSON logs with correlation IDs | Hard requirement |
| NFR-07 | Backend test coverage of services and API | >= 80% |
| NFR-08 | Recovery point objective / recovery time objective | RPO 15 min / RTO 1 h |

## 9. Assumptions

- Citizens have a smartphone with a browser and intermittent connectivity.
- Browser geolocation is available but may be coarse; manual pin adjustment is
  always offered.
- V1 operates in a single administrative region with one control centre.
- Data used before any pilot is synthetic.

## 10. Constraints

- No integration with real emergency telephony (112/108) in V1.
- No real dispatch of real resources until an authority formally onboards.
- Personal and location data is regulated; retention rules apply (see
  `SECURITY.md`).

## 11. Out of scope (permanently)

- Autonomous dispatch without human approval.
- Presenting AI inference as verified fact.
- Medical diagnosis or triage advice to citizens.

## 12. Success measures

| Measure | Definition |
|---|---|
| Time to triage | Report received -> first dispatcher action |
| Time to assignment | Report received -> resource assigned |
| Priority agreement | % of AI/engine priorities a dispatcher accepts unchanged |
| Missed-critical rate | Critical incidents initially scored below critical |
| False-critical rate | Non-critical incidents scored critical |

Missed-critical and false-critical are tracked **separately**; they are never
collapsed into a single accuracy number.

## 13. Open questions

1. Which authority owns the operating deployment and its escalation policy?
2. What is the legal retention period for citizen location data in the target
   jurisdiction?
3. Is anonymous (unauthenticated) reporting required, and how is it abuse-rated?
4. Which languages must voice reporting support at pilot?
