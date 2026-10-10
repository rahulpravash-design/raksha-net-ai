# RAKSHA NET AI — Security Architecture

This platform handles emergency reports, personal contact details and precise
location. Security is a functional requirement, not a hardening phase.

---

## 1. Threat model (summary)

| # | Threat | Control |
|---|---|---|
| T1 | Credential stuffing / password guessing | bcrypt, rate limiting, uniform login errors, per-account lockout with progressive backoff, TOTP MFA |
| T2 | Token theft | Short access TTL, rotating hashed refresh tokens, reuse detection |
| T3 | Horizontal privilege escalation (citizen reads others' reports) | Ownership checks in the service layer; 404 not 403 |
| T4 | Vertical escalation (citizen acts as dispatcher) | `require_roles` on every operational endpoint |
| T5 | Malicious upload (web shell, decompression bomb, malware) | Size cap, MIME allow-list, magic-byte sniff, generated storage key, no execution path, ClamAV scan before storage (when configured) |
| T6 | Location surveillance | Role-gated precise coordinates, analytics only on a ~1.1 km grid, coordinates never logged |
| T7 | False / spam reporting | Authenticated reporting, per-user rate limit, `REJECTED` status, audit trail |
| T8 | SQL injection | Parameterised SQLAlchemy throughout; no string-built SQL |
| T9 | Prompt injection via report text (Phase 6) | Model output validated against a strict schema; output never executes |
| T10 | Insider misuse | Append-only audit log of every sensitive action |
| T11 | Data exfiltration through logs | Structured logging with a deny-list of sensitive fields |
| T12 | Database disclosure (dump, backup, replica) | Contact numbers and MFA secrets encrypted at rest; passwords and refresh tokens hashed |
| T13 | Account lock-out used as a denial of service | Progressive (capped) lock; administrators can clear it |

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

### Passwords: change, forced change, administrator reset

* `POST /auth/password` needs the current password, and a current TOTP code when MFA is
  on (replay-protected like login). Wrong answers count toward lockout — otherwise the
  endpoint is a password-guessing oracle for anyone holding a session. The new password
  goes through the same strength rules as registration and must differ from the old.
* On success every refresh token of the account is revoked and the caller gets a fresh
  pair. **Access tokens already issued stay valid until they expire** (default 30 min):
  they are stateless, and shortening that window is the only lever. Presenting a revoked
  refresh token afterwards ends the whole chain, as for any replayed token.
* A password an administrator chose (account creation, or `reset-password`) is flagged
  `must_change_password`. Until it is replaced, every endpoint except `/auth/me`,
  `/auth/password` and `/auth/mfa/*` answers `403 PASSWORD_CHANGE_REQUIRED`, so a
  password known to someone else never stays in force.
* An administrator cannot reset their own password this way (a hijacked admin session
  could otherwise set one it knows without being asked for the old one) and only a
  super administrator manages a super administrator. Reset and change are audited
  (`auth.password_reset_by_admin`, `auth.password_changed`) without any password.
* **Recovery by email** (only when `RAKSHA_SMTP_HOST` is set):
  * `POST /auth/forgot-password` answers `202` with identical text for every address, and
    the email is sent *after* the response (so a slow mail server cannot be timed). The one
    residual difference is a single database insert for a real account; it is not masked.
  * The link is `secrets.token_urlsafe` (256-bit), stored only as a SHA-256 hash, single-use,
    valid 30 minutes (configurable), and a newer request or a completed reset spends older
    ones. Per account, at most 3 requests per hour send anything (the rest still answer `202`),
    so the form cannot flood an inbox; the per-IP auth rate limit also applies.
  * The link's base URL comes from configuration (`RAKSHA_*_APP_URL`, https required in
    staging/production), **never** from the request — a link built from a forged `Host` or
    `Origin` is how a token reaches an attacker. A test sends exactly that and checks.
  * A completed reset clears a lockout and the administrator-set flag (it proves control of
    the inbox), ends every session, and emails the owner a notice with no secret in it. It
    does **not** sign anyone in, and a second factor is still required at the next sign-in:
    email alone never gets past MFA.
  * An unusable mail server never changes a response: failures are logged (error type only,
    never credentials or message text) and the request still answers `202`.
  * Email is not a secure channel, so these messages contain a link or a notice and nothing
    about any incident. Incident notifications are never emailed.
  * Residual risk: whoever controls the inbox controls the account (minus any second factor).
    A deployment that cannot trust its users' mailboxes should leave `RAKSHA_SMTP_HOST` unset
    and keep recovery administrator-only.
* Not built: password history or expiry, and per-user notification preferences.

### Account lockout

Five consecutive failed sign-ins lock the account for 15 minutes
(`RAKSHA_ACCOUNT_LOCKOUT_THRESHOLD`, `RAKSHA_ACCOUNT_LOCKOUT_MINUTES`). Each
failure beyond the threshold doubles the lock, capped at 24 hours, and only a
successful sign-in resets the count — so waiting out a lock buys one more
guess, not a fresh batch. The counter is per account; rate limiting (section 7)
is per client address, and the two are complementary.

A locked account refuses even the correct password, and says so
(`403 ACCOUNT_LOCKED`). That discloses that the account exists; the alternative,
a uniform `401`, would leave a legitimate user guessing why they cannot sign
in. The trade was made for usability and is recorded here so it is a decision,
not an oversight.

Lockout is itself an attack surface: someone can fail on purpose to keep a
dispatcher out. The 24-hour cap bounds it, and an administrator can clear a
lock immediately (`POST /users/{id}/unlock`). Every lock and unlock is audited.

### Multi-factor authentication (TOTP)

RFC 6238 time-based codes (SHA-1, 30 s, six digits, one step of drift either
way), compatible with any standard authenticator app. Enrolment is two steps —
`/auth/mfa/enroll` issues a secret, `/auth/mfa/enable` proves it works with a
code — so a typo can never lock a person out of their own account.

- The shared secret is stored **encrypted** (section 10).
- A code that was accepted cannot be used again, even within its window
  (`users.mfa_last_step`), so a code seen over a shoulder is worthless.
- A wrong code counts toward lockout exactly as a wrong password does. With
  the password known, a six-digit code is all that is left to guess.
- A missing code does *not* count: it means the client has not asked yet.
- Disabling MFA needs the password **and** a current code, so a stolen session
  cannot strip the second factor.
- `RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL=true` blocks every non-citizen account
  from the API until it has enrolled. It is applied in the default
  current-user dependency, so a new endpoint cannot forget it; only `/auth/me`
  and `/auth/mfa/*` opt out, so a blocked user can still see why and fix it.
  It is **off by default** (development and the seeded accounts need to work)
  and a production-like environment **refuses to start** with it off.
- Recovery: an administrator can reset a user's second factor
  (`POST /users/{id}/reset-mfa`), which also revokes that user's sessions. An
  administrator cannot reset their own — that would let a hijacked admin
  session strip its own factor without the password-and-code check.

Gaps, stated plainly: there are **no recovery codes**, so a lost device needs an
administrator (and a lost device for the *only* administrator needs database
access). Enrolment has **no user interface** yet — it is API-only, and the sign-in
pages only *accept* a code. A QR code is not rendered; the `otpauth://` URI is
returned for the client to render.

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
| `HOSPITAL_OPERATOR` | See hospitals; report their own hospital's capacity; read and answer inbound-patient notices for it (Phase 12). **Cannot read incident records** — reporter, report text, contact and exact location are closed to this role (`INCIDENT_VIEW_ROLES`). |
| `ADMIN` | User and resource administration; read audit logs |
| `SUPER_ADMIN` | All of the above; manage administrators |

Least privilege is the rule: a hospital operator sees the clinical and ETA
information relevant to an inbound patient, not the reporter's contact details.

**Known discrepancy (not fixed):** the table says a `RESPONDER` reads *assigned*
incidents, but responders are in `INCIDENT_VIEW_ROLES` and can read the whole
queue. Decide whether that is intended before a pilot. The hospital-operator
equivalent was corrected on 2026-10-10 after a hospital-operator screen exposed it
(`tests/integration/test_hospital_operator_privacy.py`).

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
| Malware | With `RAKSHA_CLAMAV_HOST` set, content is streamed to ClamAV (`INSTREAM`) **before** anything is written; a flagged file is refused with `422` and audited with the signature |
| Record | Every stored file carries `scan_status`: `CLEAN`, or `UNSCANNED` |

`UNSCANNED` is a statement that no scan happened — no scanner configured, or
(with `RAKSHA_CLAMAV_REQUIRED` off) the scanner was unreachable. It is never to
be read as safe. The default is to keep the upload when the scanner is down,
because a photograph is secondary to the report it belongs to and an outage in
an optional tool must not stop a report being completed; set
`RAKSHA_CLAMAV_REQUIRED=true` to refuse instead. This is the same posture as the
AI and notification boundaries.

The scanner client is tested against a fake daemon speaking the real wire
format. **It has not been run against an actual ClamAV.**

Planned: signed short-lived URLs once object storage replaces the local backend.

## 6. Transport and headers

TLS 1.2+ everywhere outside local development; HSTS at the edge.

**The API** (JSON only) sends `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy: same-origin`,
and `Content-Security-Policy: default-src 'none'; frame-ancestors 'none';
base-uri 'none'` — a JSON API has no legitimate use for script, style or
frames. The interactive docs (`/docs`, development only) are exempt, since
Swagger UI loads its own script. `Strict-Transport-Security` is sent in a
production-like environment.

**The three Next.js apps** each send a CSP built from the origins they really
need: `connect-src` is the API origin, `img-src` adds the map tile host,
`object-src 'none'`, `frame-ancestors 'none'`, `base-uri` and `form-action`
`'self'`.

Known weakening: the front-end policy allows `'unsafe-inline'` for script and
style. Next.js emits inline bootstrap scripts and Tailwind/Leaflet set inline
styles; dropping it needs per-request nonces, which is not done. The CSP still
limits where data can be sent and what can be framed or embedded, but it does
**not** contain an XSS that injects inline script. Output escaping (section 4)
remains the primary defence.

CORS uses an explicit origin allow-list. `*` is rejected at startup in any
non-development environment, together with a default `SECRET_KEY`,
`RAKSHA_DEBUG=true`, a missing `RAKSHA_ENCRYPTION_KEY`, and MFA not being
required for operational roles — the application refuses to boot rather than
run insecurely.

---

## 7. Rate limiting

| Class | Default | Keyed by |
|---|---|---|
| Authentication | 10/min | Client IP |
| Reporting | 12/min | User ID |
| General API | 120/min | A digest of the bearer token, else the client IP |

Fixed-window counters. Exceeded limits return `429` with `Retry-After`. Emergency
reporting limits are deliberately generous: rate limiting must not become a
denial of service against a genuine emergency.

**Backend (`RAKSHA_RATE_LIMIT_BACKEND`).** `memory` counts per process, which is
right for development, tests and a single process and **wrong behind several**:
with two API processes and a limit of 10, 19 login attempts were answered (measured);
with `redis`, exactly 10. Use `redis` for any multi-process deployment. If Redis
fails, counting falls back to the local process rather than allowing everything,
Redis is not retried for a few seconds, and
`raksha_rate_limit_backend_errors_total` counts the failures — so while it is
rising the limits are weaker (up to `limit` extra requests per process per window).
A production-like environment started with `memory` logs a warning.

**Correction to earlier versions of this document.** It described Redis-backed
counters as implemented. They were not: `RAKSHA_REDIS_URL` was defined and never
read, no Redis client was ever created, and the limiter was always per-process.
The middleware also keyed clients with Python's built-in `hash()`, which differs
per process, so a shared store would not have shared anything. Both are fixed and
tested (against a real Redis, and across two real processes). No test of any kind
exercised a `429` before this; `TESTING.md` listed one.

Limits that **account lockout** (section 2) does not depend on: lockout is stored
in the database and holds regardless of this backend.

---

## 8. Audit logging

Append-only. Written for: login success and failure, account lock and unlock,
MFA enrolment, enabling, disabling and reset, logout, token reuse
detection, rejected malware uploads, role change, user activation/deactivation, incident status change,
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
- `RAKSHA_ENCRYPTION_KEY` is separate from `SECRET_KEY` on purpose: rotating the
  token-signing secret must never make stored phone numbers unreadable. List
  several comma-separated keys to rotate — the first encrypts, all decrypt (see
  the runbook). In development and test a key is derived from `SECRET_KEY`
  instead; that fallback is refused in a production-like environment.

## 10. Data protection

| Control | Status |
|---|---|
| Encryption in transit | TLS everywhere outside local dev |
| Encryption at rest | Managed-database volume encryption (deployment) |
| Column-level encryption of contact details | **Implemented.** `contact_phone` on incidents, resources and hospitals, and `users.mfa_secret` |
| Backups | Encrypted, tested restore, 30-day retention (procedure documented; not yet exercised in a real deployment) |
| Retention / coarsening | `DATABASE.md` §6 |
| Deletion | Account deletion nulls the reporter link and purges contact fields; incident records survive for emergency-record integrity |

**What column-level encryption does.** Fernet (AES-128-CBC with an HMAC, so
tampering is detected). A database dump, a backup or a read replica yields
ciphertext for these columns. It is transparent to the application
(`EncryptedString`, `app/db/types.py`).

**What it does not do.** It does not protect against an attacker who holds the
running application *and* its key; the key must therefore live in a secret
manager, not beside the data. It does not cover `users.phone` (unique and looked
up; randomised ciphertext supports neither) or `users.email`. Those, and the
free-text incident description, remain plaintext. Raw SQL bypasses the column
type, so any hand-written query that selects an encrypted column must call
`decrypt_value` itself (the hospital nearby query does).

A value that cannot be decrypted (wrong key, tampering) raises rather than
returning ciphertext: showing a responder garbage where a phone number belongs,
silently, during an emergency is worse than an error that gets noticed.

## 11. Dependency and supply chain

- Pinned versions in `requirements.txt` and `package-lock.json`.
- `pip-audit --strict` (full transitive resolution) and `npm audit --omit=dev
  --audit-level=high` run in CI **and** in `scripts/check.sh`, so the local gate
  is the CI gate. A finding fails the build.
- The npm gate covers **production dependencies only**. Dev tooling is never
  shipped, and today carries one known advisory (`braces`, a ReDoS, inside the
  ESLint config chain) whose fix needs a breaking `--force` upgrade. It is
  reported by `npm audit` but deliberately not gating; revisit when the toolchain
  can be upgraded.
- The first run of these audits found real advisories (PyJWT, three in Next.js
  including a critical, two transitive npm packages). They were fixed, not waived.
- Dependabot for updates.
- No dependency added without justification (`CLAUDE.md` §3).

## 12. What is and is not done (Phase 16 status)

**Built and tested:** account lockout, TOTP MFA with optional enforcement for
operational roles, administrative unlock and MFA reset, contact-detail and
MFA-secret encryption, API and front-end security headers and CSP, malware
scanning of uploads (interface, ClamAV client, honest `UNSCANNED`), and
dependency-audit gating.

**Not done, and not claimable by software:**

- **No penetration test has been performed.** It is a human, independent act.
  Everything above is evidence of intent and unit/integration testing, not of
  having survived an adversary.
- **No operating authority has accepted the residual risk.**
- **The malware scanner has not been run against a real ClamAV.**
- **The front-end CSP allows `'unsafe-inline'`** (section 6).
- **MFA has no enrolment UI and no recovery codes** (section 2).
- **MFA enforcement is off by default** and must be turned on (a production-like
  environment will not start without it).
- **Lockout and MFA were verified against a local stack** — not under load, not
  behind a real proxy and TLS terminator, and not with real authenticator
  hardware (an independent TOTP implementation was used for interoperability).
- Dev-tooling advisories are not gated (section 11).

**The platform must not be used for real emergency operations** until a
penetration test has been done and its findings remediated, and an authority has
accepted the residual risk. Phase 16's code is necessary for that, not sufficient.
