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
| GET | `/auth/me` | access token | Current user profile |

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
{"email": "asha@example.com", "password": "correct horse battery"}
```
`200`:
```json
{
  "access_token": "eyJ…", "token_type": "bearer", "expires_in": 1800,
  "refresh_token": "8f2b…", "user": { "id": "…", "role": "CITIZEN", "…": "…" }
}
```
`401 INVALID_CREDENTIALS` for both unknown email and wrong password — the
responses are indistinguishable by design.

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
| GET | `/users` | ADMIN, SUPER_ADMIN | List users (filter `role`, `is_active`, `q`) |
| POST | `/users` | ADMIN, SUPER_ADMIN | Create a user with any role |
| GET | `/users/{id}` | ADMIN, SUPER_ADMIN | Read a user |
| PATCH | `/users/{id}` | ADMIN, SUPER_ADMIN | Update role / active flag |

Only `SUPER_ADMIN` may create or modify a `SUPER_ADMIN`. No role may modify
its own `role` or `is_active` field.

---

## 5. Incidents

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/incidents` | CITIZEN+ | Report an emergency |
| GET | `/incidents/mine` | CITIZEN+ | Own reports |
| GET | `/incidents` | DISPATCHER, ADMIN, SUPER_ADMIN, RESPONDER | Queue with filters |
| GET | `/incidents/{id}` | owner or operational role | Incident detail |
| PATCH | `/incidents/{id}` | DISPATCHER+ | Update verified facts |
| POST | `/incidents/{id}/status` | owner (cancel only) or DISPATCHER+ | Transition status |
| POST | `/incidents/{id}/priority` | DISPATCHER+ | Recompute or override priority |
| POST | `/incidents/{id}/assign` | DISPATCHER+ | Assign to an operator |
| GET | `/incidents/{id}/history` | owner or operational role | Status history |
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

## 6. Media

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/incidents/{id}/media` | owner or DISPATCHER+ | Upload an image (multipart) |
| GET | `/incidents/{id}/media` | owner or operational role | List media metadata |
| GET | `/media/{media_id}/content` | owner or operational role | Stream the bytes |

Validation: size <= `RAKSHA_MEDIA_MAX_BYTES`, declared MIME in the allow-list,
**and** magic-byte sniffing that must agree with the declared type. The stored
key is generated; the client filename is never used as a path component.

---

## 7. Geo

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/geo/incidents/nearby` | operational role | Incidents within a radius |
| GET | `/geo/incidents/bbox` | operational role | Incidents in a viewport, as GeoJSON |

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

## 8. Planned endpoints (not implemented)

| Phase | Endpoint | Purpose |
|---|---|---|
| 5 | `WS /api/v1/ws/incidents` | Live incident stream for the control centre |
| 6 | `POST /incidents/{id}/analyze` | Request AI analysis |
| 6 | `GET /incidents/{id}/analyses` | AI proposals with confidence |
| 6 | `POST /analyses/{id}/review` | Accept / edit / reject a proposal |
| 9 | `POST /reports/voice` | Voice report upload and transcription |
| 10 | `GET /resources`, `GET /geo/resources/nearby` | Resource inventory and search |
| 11 | `POST /incidents/{id}/dispatch` | Human-approved dispatch |
| 11 | `POST /assignments/{id}/status` | Responder progress |
| 12 | `GET /hospitals/{id}/capacity` | Hospital capacity |
| 13 | `GET /notifications` | Notification inbox |
| 14 | `GET /analytics/*` | Aggregated metrics |

All planned endpoints follow the conventions above. `POST /incidents/{id}/dispatch`
always requires an authenticated human dispatcher; there is no service-account
path to it.
