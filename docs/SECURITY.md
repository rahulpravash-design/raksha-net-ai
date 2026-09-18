# RAKSHA NET AI — Security Architecture

This platform handles emergency reports, personal contact details and precise
location. Security is a functional requirement, not a hardening phase.

---

## 1. Threat model (summary)

| # | Threat | Control |
|---|---|---|
| T1 | Credential stuffing | bcrypt, rate limiting, uniform login errors |
| T2 | Token theft | Short access TTL, rotating hashed refresh tokens, reuse detection |
| T3 | Horizontal privilege escalation (citizen reads others' reports) | Ownership checks in the service layer; 404 not 403 |
| T4 | Vertical escalation (citizen acts as dispatcher) | `require_roles` on every operational endpoint |
| T5 | Malicious upload (web shell, decompression bomb) | Size cap, MIME allow-list, magic-byte sniff, generated storage key, no execution path |
| T6 | Location surveillance | Role-gated precise coordinates, coarsening on retention, coordinates never logged |
| T7 | False / spam reporting | Authenticated reporting, per-user rate limit, `REJECTED` status, audit trail |
| T8 | SQL injection | Parameterised SQLAlchemy throughout; no string-built SQL |
| T9 | Prompt injection via report text (Phase 6) | Model output validated against a strict schema; output never executes |
| T10 | Insider misuse | Append-only audit log of every sensitive action |
| T11 | Data exfiltration through logs | Structured logging with a deny-list of sensitive fields |

## 2. Authentication

- **Password hashing:** bcrypt, cost 12 (configurable). Hashes are never
  logged, returned, or included in an audit payload.
- **Password policy:** minimum 12 characters (configurable). Length is favoured
  over composition rules; the check rejects the obvious worst cases rather than
  forcing unmemorable strings.
- **Access token:** JWT, HS256, 30-minute TTL, carrying `sub`, `role`, `jti`,
  `iat`, `exp`, `type=access`. It is a bearer credential: short-lived by design.
- **Refresh token:** opaque 64-byte random value. Only its SHA-256 is stored.
  Rotated on every use; the presented token is revoked as part of the same
  transaction.
- **Reuse detection:** presenting an already-revoked refresh token revokes the
  entire descendant chain and forces re-authentication. This is how stolen
  refresh tokens are caught.
- **Uniform failure:** unknown email and wrong password return the same
  `401 INVALID_CREDENTIALS` after comparable work, so the endpoint is not a user
  enumeration oracle.

Planned: TOTP MFA for `DISPATCHER` and above (Phase 16); account lockout with
progressive backoff.

## 3. Authorisation

Two independent checks, both enforced server-side:

1. **Role check** — `require_roles(...)` as a FastAPI dependency. Declared per
   endpoint; there is no implicit default.
2. **Ownership check** — in the service layer. A `CITIZEN` may read, and cancel,
   only an incident they reported.

| Role | Capability |
|---|---|
| `CITIZEN` | Create a report; read/cancel own reports; upload media to own reports |
| `RESPONDER` | Read assigned incidents; update assignment status (Phase 11) |
| `DISPATCHER` | Read all incidents; transition status; override priority; assign; dispatch |
| `HOSPITAL_OPERATOR` | Read incidents routed to their hospital; report capacity (Phase 12) |
| `ADMIN` | User and resource administration; read audit logs |
| `SUPER_ADMIN` | All of the above; manage administrators |

Least privilege is the rule: a hospital operator sees the clinical and ETA
information relevant to an inbound patient, not the reporter's contact details.

## 4. Input validation

- Every request body and query string is a Pydantic model with explicit bounds.
- Free text has maximum lengths and is stored as-is, escaped at render time —
  never sanitised destructively on input.
- Coordinates are range- and bbox-validated (`GIS_ARCHITECTURE.md` §3).
- Enums are validated by both Pydantic and the PostgreSQL enum type.
- Pagination bounds are enforced (`page_size` <= 100) to prevent resource
  exhaustion by a large page request.

## 5. File uploads

| Control | Implementation |
|---|---|
| Size | Streaming cap at `RAKSHA_MEDIA_MAX_BYTES`; oversize -> `413` |
| Type | Declared MIME must be in the allow-list **and** match sniffed magic bytes |
| Name | Storage key is `{incident_id}/{uuid4}{ext}`; the client filename is metadata only |
| Location | Outside the web root; served through an authorised endpoint only |
| Execution | Storage directory is never on an execution path; no server-side rendering of uploads |
| Integrity | SHA-256 recorded per object |

Planned: antivirus scanning in the ingestion path (Phase 16), and signed
short-lived URLs once object storage replaces the local backend.

## 6. Transport and headers

TLS 1.2+ everywhere outside local development; HSTS at the edge. Responses
carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, and a CSP that forbids inline script and
restricts `img-src`/`connect-src` to the API and the configured tile host.

CORS uses an explicit origin allow-list. `*` is rejected at startup in any
non-development environment, together with a default `SECRET_KEY` and
`RAKSHA_DEBUG=true` — the application refuses to boot rather than run insecurely.

## 7. Rate limiting

| Class | Default | Keyed by |
|---|---|---|
| Authentication | 10/min | Client IP |
| Reporting | 12/min | User ID |
| General API | 120/min | User ID, else IP |

Fixed-window counters in Redis (in-memory fallback for single-process
development). Exceeded limits return `429` with `Retry-After`. Emergency
reporting limits are deliberately generous: rate limiting must not become a
denial of service against a genuine emergency.

## 8. Audit logging

Append-only. Written for: login success and failure, logout, token reuse
detection, role change, user activation/deactivation, incident status change,
priority override, assignment, media access, and every administrative action.

Each entry records actor, actor role, action, entity, IP, user agent, timestamp
and a metadata object. The metadata object is explicitly filtered: no tokens, no
password material, no full coordinate pairs.

No application code path updates or deletes an audit row.

## 9. Logging and secrets

- Structured JSON logs with a correlation ID per request.
- Deny-list at the formatter: `password`, `hashed_password`, `token`,
  `refresh_token`, `authorization`, `secret`, `api_key`, `latitude`,
  `longitude`.
- Secrets come from the environment; in production from a managed secret store
  (AWS Secrets Manager / Vault / equivalent). `.env` is git-ignored and
  `.env.example` contains only placeholders.
- Key rotation: `SECRET_KEY` rotation invalidates access tokens by design;
  refresh tokens survive because they are opaque and stored, allowing rotation
  without logging everyone out.

## 10. Data protection

| Control | Status |
|---|---|
| Encryption in transit | TLS everywhere outside local dev |
| Encryption at rest | Managed-database volume encryption |
| Column-level encryption for contact details | Planned, Phase 16 |
| Backups | Encrypted, tested restore, 30-day retention |
| Retention / coarsening | `DATABASE.md` §6 |
| Deletion | Account deletion nulls the reporter link and purges contact fields; incident records survive for emergency-record integrity |

## 11. Dependency and supply chain

- Pinned versions in `requirements.txt` and `package-lock.json`.
- `pip-audit` and `npm audit` in CI; a high-severity advisory fails the build.
- Dependabot for updates.
- No dependency added without justification (`CLAUDE.md` §3).

## 12. Deliberate security non-goals for V1

These are documented so they are not mistaken for oversights:

- No MFA (Phase 16).
- No anti-virus scanning of uploads (Phase 16).
- No column-level encryption (Phase 16).
- No formal penetration test before a pilot is scheduled.

**The platform must not be used for real emergency operations until the Phase 16
items are complete and an authority has accepted the residual risk.**
