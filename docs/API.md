# RAKSHA NET AI — API Specification

Base path: `/api/v1` · Format: JSON · Auth: `Authorization: Bearer <access_token>`

Interactive documentation is served at `/docs` when `RAKSHA_DEBUG=true`.

---

## 1. Conventions

- All timestamps are ISO-8601 UTC (`2026-01-31T09:14:00Z`).
- All identifiers are UUID v4 strings.
- Every response carries `X-Request-ID`; send your own to correlate logs.
- Pagination: `?page=1&page_size=25` (`page_size` max 100). List responses are
  `{ "items": [...], "total": n, "page": p, "page_size": s, "pages": k }`.

### Who may do what

- **operational** — `RESPONDER`, `DISPATCHER`, `HOSPITAL_OPERATOR`, `ADMIN`,
  `SUPER_ADMIN`.
- **dispatch side** (`DISPATCH roles`, also `DISPATCHER+`) — `DISPATCHER`,
  `ADMIN`, `SUPER_ADMIN`. This is also the set that may **read incident records**
  (`INCIDENT_VIEW_ROLES`): responders and hospital operators are operational but
  cannot read an incident. A responder reaches only the assignments dispatched to a
  unit they operate (`/dispatches/mine`, `/dispatches/{id}`); a hospital operator
  only the notices addressed to their hospital. Where a label below says
  *owner or dispatch side*, the owner is the citizen who reported it.

### Error format

```json
{
  "error": {
    "code": "INCIDENT_INVALID_TRANSITION",
    "message": "Cannot move incident from RESOLVED to ASSIGNED.",
    "details": {"from": "RESOLVED", "to": "ASSIGNED"},
    "request_id": "0f4c…"
  }
}
```

| HTTP | Code family | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR`, `*_INVALID_*` | Malformed or rejected input |
| 401 | `NOT_AUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` | Auth required/failed |
| 403 | `FORBIDDEN` | Authenticated but not permitted |
| 404 | `NOT_FOUND` | Absent, or not visible to this caller |
| 409 | `CONFLICT`, `EMAIL_ALREADY_REGISTERED` | State conflict |
| 413 | `MEDIA_TOO_LARGE` | Upload exceeds cap |
| 415 | `MEDIA_UNSUPPORTED_TYPE` | MIME not allowed |
| 429 | `RATE_LIMITED` | Too many requests (`Retry-After` set) |
| 500 | `INTERNAL_ERROR` | Unhandled — details never leaked |

A citizen requesting another citizen's incident receives **404, not 403**, so
the API does not confirm that the incident exists.

---

## 2. Health

### `GET /api/v1/health`
Unauthenticated liveness probe.
```json
{"status": "ok", "environment": "development", "version": "1.0.0"}
```

### `GET /api/v1/health/ready`
Readiness probe — verifies a database round trip and reports PostGIS.
```json
{"status": "ok", "database": "ok", "postgis": "3.4", "checks": {"database_latency_ms": 1.8}}
```
Returns **503** with `"status": "degraded"` if the database is unreachable.

---

## 3. Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | none | Register a citizen account |
| POST | `/auth/login` | none | Exchange credentials for tokens |
| POST | `/auth/refresh` | refresh token | Rotate tokens |
| POST | `/auth/logout` | refresh token | Revoke a refresh token |
| GET | `/auth/me` | access token | Current user profile (exempt from the MFA policy) |
| GET | `/auth/recovery-status` | none | `{"email_available": bool}` — whether this deployment can send recovery email, so a screen can say "ask an administrator" instead of promising a message |
| POST | `/auth/forgot-password` | none | Ask for a recovery link. **Always `202` with the same body** for any address; an email is sent after the response, only for an active account with allowance left this hour |
| POST | `/auth/reset-password` | none | `{token, new_password}`: spend a recovery link. Does not sign anyone in. One `400 INVALID_RESET_TOKEN` for unknown, expired, used and replaced links; a weak password (`400 WEAK_PASSWORD`) does not spend the link |
| POST | `/auth/password` | access token | Change your own password. Needs `current_password` (and `mfa_code` when MFA is on). Ends every other session and returns a fresh token pair. Exempt from the account policies, so a user who must change an administrator-set password can reach it |
| POST | `/auth/mfa/enroll` | access token | Begin TOTP enrolment; returns the shared secret and an `otpauth://` URI |
| POST | `/auth/mfa/enable` | access token | Confirm enrolment with a code; MFA is on from here |
| POST | `/auth/mfa/disable` | access token | Turn MFA off; needs the password **and** a current code |

Rate limit: `RAKSHA_RATE_LIMIT_AUTH_PER_MINUTE` (default 10/min per IP).

### `POST /auth/register`
```json
{"email": "asha@example.com", "password": "correct horse battery", "full_name": "Asha R", "phone": "+919876543210"}
```
`201` -> `UserRead`. `409 EMAIL_ALREADY_REGISTERED` on duplicate.
Self-registration always creates a `CITIZEN`. Operational roles are created by
an administrator; a `role` field in this request body is ignored.

### `POST /auth/login`
```json
{"email": "asha@example.com", "password": "correct horse battery", "mfa_code": "123456"}
```
`mfa_code` (six digits) is required only for an account with MFA enabled.
`200`:
```json
{
  "access_token": "eyJ…", "token_type": "bearer", "expires_in": 1800,
  "refresh_token": "8f2b…", "user": { "id": "…", "role": "CITIZEN", "…": "…" }
}
```
`401 INVALID_CREDENTIALS` for both unknown email and wrong password — the
responses are indistinguishable by design.

Further sign-in outcomes:

| Status | Code | Meaning |
|---|---|---|
| 401 | `MFA_REQUIRED` | The password was right and the account has MFA on; repeat the request with `mfa_code`. Does not count toward lockout. |
| 401 | `INVALID_MFA_CODE` | Wrong, expired, or already-used code. **Counts toward lockout.** |
| 403 | `ACCOUNT_LOCKED` | Too many failures. `details.retry_after_seconds` says how long. The correct password is refused too until the lock expires. |
| 403 | `ACCOUNT_INACTIVE` | The account is deactivated. |
| 403 | `PASSWORD_CHANGE_REQUIRED` | Returned by any endpoint other than `/auth/me`, `/auth/password` and `/auth/mfa/*` while `must_change_password` is true — i.e. an administrator chose this account's password (creation or reset). |
| 403 | `MFA_ENROLLMENT_REQUIRED` | Returned by any endpoint other than `/auth/me` and `/auth/mfa/*` when `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL` is on and a non-citizen account has not enrolled. |

Five consecutive failures lock the account for 15 minutes (configurable); each
further failure doubles the lock, capped at 24 hours. Only a successful sign-in
resets the count. The MFA management endpoints answer a wrong code with
`400 INVALID_MFA_CODE` rather than 401, so a client does not mistake it for an
expired session. `POST /auth/password` does the same for a wrong current password
(`400 INVALID_CREDENTIALS`), a wrong or missing MFA code (`400 INVALID_MFA_CODE`) and a
new password equal to the old one (`400 PASSWORD_UNCHANGED`); the first two **count toward
lockout**, so a stolen session cannot be used to guess the password.

### `POST /auth/refresh`
`{"refresh_token": "8f2b…"}` -> new access **and** refresh token; the presented
token is revoked. Presenting an already-revoked token revokes the entire chain
and returns `401`.

---

## 4. Users

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/me` | any | Own profile |
| PATCH | `/users/me` | any | Update own `full_name`, `phone` |
| GET | `/users` | ADMIN, SUPER_ADMIN | List users (filter `role`, `is_active`, `q`). Includes `locked_until` and `failed_login_attempts`, which the self view (`/users/me`) does not |
| GET | `/users/directory` | DISPATCH roles | Active responders only — `id`, `full_name`, `role` and nothing else. For linking a crew member to a unit |
| POST | `/users` | ADMIN, SUPER_ADMIN | Create a user with any role |
| GET | `/users/{id}` | ADMIN, SUPER_ADMIN | Read a user |
| PATCH | `/users/{id}` | ADMIN, SUPER_ADMIN | Update role / active flag |
| POST | `/users/{id}/unlock` | ADMIN, SUPER_ADMIN | Clear an account lockout |
| POST | `/users/{id}/reset-password` | ADMIN, SUPER_ADMIN | Set a temporary password (`new_password`): ends the user's sessions, clears any lockout and makes them change it at first sign-in. Not permitted on yourself |
| POST | `/users/{id}/reset-mfa` | ADMIN, SUPER_ADMIN | Remove a user's second factor and revoke their sessions. Not permitted on yourself. |

Only `SUPER_ADMIN` may create or modify a `SUPER_ADMIN`. No role may modify
its own `role` or `is_active` field.

---

## 5. Incidents

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/incidents` | CITIZEN+ | Report an emergency |
| GET | `/incidents/mine` | CITIZEN+ | Own reports |
| GET | `/incidents` | dispatch side | Queue with filters |
| GET | `/incidents/{id}` | owner or dispatch side | Incident detail |
| PATCH | `/incidents/{id}` | DISPATCHER+ | Update verified facts |
| POST | `/incidents/{id}/status` | owner (cancel only) or DISPATCHER+ | Transition status |
| POST | `/incidents/{id}/priority` | DISPATCHER+ | Recompute or override priority |
| POST | `/incidents/{id}/assign` | DISPATCHER+ | Assign to dispatch staff. Responders and hospital operators are refused (`400`): field units are sent with a dispatch |
| GET | `/incidents/{id}/history` | owner or dispatch side | Status history |
| GET | `/incidents/stats/summary` | DISPATCHER+ | Counts by band and status |

### `POST /incidents`
```json
{
  "category": "FLOOD",
  "description": "Five people trapped inside a house, water rising fast.",
  "latitude": 13.0827, "longitude": 80.2707,
  "address_text": "2nd Street, Kotturpuram",
  "landmark": "Opposite the water tank",
  "people_affected": 5,
  "people_trapped": true,
  "medical_required": true,
  "immediate_danger": true,
  "contact_phone": "+919876543210"
}
```
`201` -> `IncidentRead` including `reference_code`, `priority_score`,
`priority_band` and `priority_factors`. The incident is created in status
`REPORTED` and an initial history row is written.

Rate limit: `RAKSHA_RATE_LIMIT_REPORT_PER_MINUTE` (default 12/min per user).

### `GET /incidents`
Query parameters: `status` (repeatable), `category` (repeatable),
`priority_band`, `q` (free text over description/reference), `since`, `until`,
`assigned_to_me`, `sort` (`priority` default, `created_at`, `-created_at`),
`page`, `page_size`.

### `POST /incidents/{id}/status`
```json
{"status": "UNDER_REVIEW", "note": "Calling the reporter to confirm."}
```
`409 INCIDENT_INVALID_TRANSITION` if the state machine forbids it.

### `POST /incidents/{id}/priority`
```json
{"override_band": "CRITICAL", "reason": "Reporter confirmed a collapsed wall by phone."}
```
`reason` is mandatory when overriding. Omitting `override_band` recomputes the
score from current facts. Both paths write an audit entry.

---

## 5a. AI analysis

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/incidents/{id}/analyses` | dispatch side | Request an AI proposal |
| GET | `/incidents/{id}/analyses` | dispatch side | List proposals for an incident |
| POST | `/incidents/{id}/analyses/{analysis_id}/review` | DISPATCHER+ | Accept, edit or reject a proposal |

A proposal is never a fact: `IncidentAnalysisRead` is a separate resource from
`IncidentRead`, and nothing here writes to an incident by itself
(`docs/AI_ARCHITECTURE.md` section 1).

### `POST /incidents/{id}/analyses`
No body. Runs the configured analyzer (`ai/nlp/text_analyzer.py` in V2 — a
rule-based baseline, `docs/AI_ARCHITECTURE.md` section 7) against the report's
own description and persists the result.

`201` -> `IncidentAnalysisRead`, always with `review_decision: null`.
`503 ANALYSIS_UNAVAILABLE` if `RAKSHA_AI_ENABLED` is false or the analyzer
raised — the incident remains fully usable either way.
`422 ANALYSIS_REJECTED` if the model's own output failed validation (an
out-of-vocabulary observation, an implausible headcount, an internally
inconsistent proposal); the reasons are returned and nothing is stored.

### `POST /incidents/{id}/analyses/{analysis_id}/review`
```json
{"decision": "ACCEPTED", "note": "Matches the photos too."}
```
```json
{"decision": "EDITED", "category": "FIRE", "people_affected": 9,
 "note": "Reporter called back; it's a fire, not a flood."}
```
```json
{"decision": "REJECTED", "note": "Description does not support this."}
```
`ACCEPTED` applies the proposal's own values; `EDITED` applies the values
given in the request instead. Either way, applied fields go through the exact
same path as `PATCH /incidents/{id}` — priority is recomputed and the change
is audited. `REJECTED` changes nothing on the incident. An analysis can be
reviewed once: a second attempt gets `409 ANALYSIS_ALREADY_REVIEWED`.

---

## 6. Media

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/incidents/{id}/media` | owner or DISPATCHER+ | Upload an image (multipart) |
| GET | `/incidents/{id}/media` | owner or dispatch side | List media metadata |
| GET | `/media/{media_id}/content` | owner or dispatch side | Stream the bytes |

Validation: size <= `RAKSHA_MEDIA_MAX_BYTES`, declared MIME in the allow-list,
**and** magic-byte sniffing that must agree with the declared type. The stored
key is generated; the client filename is never used as a path component.
**Embedded metadata (EXIF GPS, device identifiers, XMP, IPTC, comments) is stripped
before storage**, so `size_bytes` and the content served back describe the cleaned
file and are usually smaller than the upload. A JPEG keeps only its orientation. An
image whose structure cannot be read is refused with `400`.

Malware scanning: with `RAKSHA_CLAMAV_HOST` set, content is scanned before it
is stored. A flagged file is refused with `422 MEDIA_INFECTED` and never
written. Every stored item carries `scan_status`: `CLEAN`, or `UNSCANNED` when no
scanner is configured (or it was unreachable and `RAKSHA_CLAMAV_REQUIRED` is
off). `UNSCANNED` is a statement that no scan happened, not that the file is safe.
With `RAKSHA_CLAMAV_REQUIRED=true`, an unreachable scanner yields
`503 MEDIA_SCAN_UNAVAILABLE` instead.

---

## 7. Geo

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/geo/incidents/nearby` | dispatch side | Incidents within a radius |
| GET | `/geo/incidents/bbox` | dispatch side | Incidents in a viewport, as GeoJSON |

### `GET /geo/incidents/nearby?latitude=13.08&longitude=80.27&radius_km=5&limit=50`
```json
{"items": [{"id": "…", "reference_code": "RKS-8F3K2Q", "category": "FLOOD",
            "priority_band": "CRITICAL", "distance_km": 1.42, "…": "…"}],
 "count": 1}
```
`radius_km` is capped by `RAKSHA_GEO_MAX_SEARCH_RADIUS_KM`.

### `GET /geo/incidents/bbox?min_lat=…&min_lon=…&max_lat=…&max_lon=…`
Returns a GeoJSON `FeatureCollection`; each feature's properties carry the
incident summary used by the map.

---

## 8. Resources, dispatch, hospitals, notifications and analytics (Phases 10–14)

### Resources and dispatch

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/resources` | DISPATCH roles | Register a resource |
| GET | `/resources` | operational | Resource inventory |
| GET | `/resources/stats/summary` | operational | Counts by status and type |
| GET | `/resources/nearby` | operational | Resources within a radius of a point |
| GET | `/resources/{id}` | operational | Resource detail |
| PATCH | `/resources/{id}` | DISPATCH roles | Update a resource |
| POST | `/resources/{id}/status` | DISPATCH roles, or the unit's own operator | Set operational status |
| GET | `/incidents/{id}/resource-recommendations` | dispatch side | Ranked suggestions, with reasons. Never dispatches. |
| POST | `/incidents/{id}/dispatches` | DISPATCH roles | Dispatch a resource. The approver is the authenticated caller; the body cannot name one. |
| GET | `/incidents/{id}/dispatches` | dispatch side | Resources sent to an incident |
| GET | `/dispatches/mine` | operational | The caller's own assignments (a responder's whole view of an incident: a scene brief without the reporter) |
| GET | `/dispatches/{id}` | DISPATCH roles, or the unit's operator | Dispatch detail |
| POST | `/dispatches/{id}/status` | DISPATCH roles, or the unit's operator | Progress; a legal-transition table applies |

### Hospitals

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/hospitals` | ADMIN | Register a hospital |
| PATCH | `/hospitals/{id}` | ADMIN | Correct name, position (latitude and longitude together), address, phone, linked operator (`null` unlinks), or `is_active`. The code and the capacity fields are refused (`400`); retiring is refused with `409 HOSPITAL_HAS_OPEN_NOTICES` while inbound notices are open. The audit entry records field names only |
| GET | `/hospitals` | operational | Hospitals |
| GET | `/hospitals/nearby` | operational | Hospitals that can take a patient now |
| GET | `/hospitals/{id}` | operational | Hospital detail |
| POST | `/hospitals/{id}/capacity` | the hospital's operator, or DISPATCH roles | Report capacity |
| GET | `/hospitals/{id}/notices` | the hospital's operator, or DISPATCH roles | Inbound patients |
| POST | `/incidents/{id}/hospital-notices` | DISPATCH roles | Tell a hospital what is coming |
| GET | `/incidents/{id}/hospital-notices` | dispatch side | Hospitals notified for an incident |
| POST | `/hospital-notices/{id}/status` | the hospital's operator, or DISPATCH roles | Acknowledge, divert or close |

A notice carries no reporter identity, contact detail, description or
coordinate: the record has no column for them.

### Notifications

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/notifications` | the recipient | Own inbox, with per-channel delivery records |
| GET | `/notifications/unread-count` | the recipient | Badge count |
| POST | `/notifications/{id}/read` | the recipient | Mark one read (someone else's reads as 404) |
| POST | `/notifications/read-all` | the recipient | Mark everything read |

Only the in-app channel delivers. SMS, email and push are recorded as
`UNAVAILABLE` with a reason.

### Analytics

All five are read-only and restricted to DISPATCH roles. Each accepts `since`
and `until`; the time metrics and hotspots also accept `category`.

| Method | Path | Description |
|---|---|---|
| GET | `/analytics/response-time` | Report to first dispatch, in minutes |
| GET | `/analytics/resolution-time` | Report to resolved, in minutes |
| GET | `/analytics/category-breakdown` | Counts and average priority by category |
| GET | `/analytics/resource-utilization` | Dispatches per resource type |
| GET | `/analytics/hotspots` | Incident counts per ~1.1 km grid cell. Coordinates are cell centres, never an incident's own. |

---

## 9. Planned endpoints (not implemented)

| Phase | Endpoint | Purpose |
|---|---|---|
| 5 | `WS /api/v1/ws/incidents` | Live incident stream for the control centre |
| 9 | `POST /reports/voice` | Voice report upload and transcription |
