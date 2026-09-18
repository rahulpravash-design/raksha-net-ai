# RAKSHA NET AI — Database Architecture

Engine: **PostgreSQL 16 + PostGIS 3** · Migrations: **Alembic**

---

## 1. Conventions

- Primary keys are `UUID` (`gen_random_uuid()` via `pgcrypto`/`uuid-ossp`, or
  application-generated `uuid4`).
- Timestamps are `TIMESTAMPTZ`, always UTC, named `created_at` / `updated_at`.
- Enumerations are stored as PostgreSQL `ENUM` types so the database rejects
  invalid values.
- Constraint naming follows the convention in `app/db/base.py`
  (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) so Alembic can autogenerate safely.
- Soft delete is used only where retention policy requires it
  (`deleted_at`); everything else is hard-deleted or archived.
- Geography columns are `geography(Point, 4326)` with a `GIST` index.

## 2. Phase 1 tables (implemented in V1)

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `email` | citext-like varchar, unique | stored lower-cased |
| `phone` | varchar(32), nullable, unique | E.164 |
| `hashed_password` | varchar(255) | bcrypt |
| `full_name` | varchar(160) | |
| `role` | enum `user_role` | see below |
| `is_active` | boolean, default true | |
| `is_verified` | boolean, default false | email/phone verification (Phase 13) |
| `last_login_at` | timestamptz null | |
| `created_at` / `updated_at` | timestamptz | |

`user_role`: `CITIZEN`, `RESPONDER`, `DISPATCHER`, `HOSPITAL_OPERATOR`,
`ADMIN`, `SUPER_ADMIN`.

Roles are a single column rather than a join table in V1. A
`roles` / `user_roles` pair is specified for Phase 10, when a responder may
also hold a dispatcher role; the migration path is additive.

### `refresh_tokens`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK -> users, cascade | indexed |
| `token_hash` | varchar(128), unique | SHA-256 of the opaque token |
| `expires_at` | timestamptz | |
| `revoked_at` | timestamptz null | set on rotation or logout |
| `replaced_by_id` | uuid null FK -> refresh_tokens | rotation chain |
| `user_agent` / `ip_address` | varchar null | session forensics |
| `created_at` | timestamptz | |

The raw token is never stored. Reuse of a revoked token revokes the whole
chain — detection of token theft.

### `incidents`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `reference_code` | varchar(20) unique | human-usable, e.g. `RKS-8F3K2Q` |
| `reported_by_id` | uuid FK -> users, null on account deletion | |
| `category` | enum `incident_category` | |
| `description` | text | 10..4000 chars |
| `latitude` / `longitude` | numeric(9,6) / numeric(9,6) | durable value |
| `geom` | geography(Point,4326) | GIST-indexed query value |
| `address_text` | varchar(400) null | reverse geocode or citizen text |
| `landmark` | varchar(200) null | |
| `status` | enum `incident_status` | default `REPORTED` |
| `severity` | enum `severity_level` null | operator/AI assessed |
| `priority_score` | integer null | 0..100, engine output |
| `priority_band` | enum `priority_band` null | CRITICAL/HIGH/MEDIUM/LOW |
| `priority_factors` | jsonb null | explanation of the score |
| `priority_overridden` | boolean default false | |
| `people_affected` | integer null, `>= 0` | |
| `people_trapped` | boolean default false | |
| `medical_required` | boolean default false | |
| `immediate_danger` | boolean default false | |
| `contact_phone` | varchar(32) null | |
| `assigned_to_id` | uuid null FK -> users | dispatcher-owned |
| `resolved_at` / `closed_at` | timestamptz null | |
| `duplicate_of_id` | uuid null FK -> incidents | set with status `DUPLICATE` |
| `created_at` / `updated_at` | timestamptz | |

`incident_category`: `FLOOD`, `FIRE`, `ROAD_ACCIDENT`, `MEDICAL`,
`BUILDING_COLLAPSE`, `MISSING_PERSON`, `LANDSLIDE`, `INDUSTRIAL_ACCIDENT`,
`GAS_LEAK`, `ELECTRICAL_HAZARD`, `OTHER`.

`incident_status`: `REPORTED`, `RECEIVED`, `UNDER_REVIEW`, `PRIORITIZED`,
`ASSIGNED`, `RESPONDER_EN_ROUTE`, `ON_SCENE`, `RESOLVED`, `CLOSED`,
`CANCELLED`, `DUPLICATE`, `REJECTED`.

Indexes: `status`, `category`, `priority_score DESC`, `created_at DESC`,
`reported_by_id`, and `GIST(geom)`. Composite `(status, priority_score DESC)`
serves the control-centre queue.

### `incident_media`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `incident_id` | uuid FK -> incidents, cascade | indexed |
| `uploaded_by_id` | uuid null FK -> users | |
| `media_type` | enum `media_type` | `IMAGE`, `AUDIO`, `VIDEO` |
| `storage_key` | varchar(400) | generated, never client-supplied |
| `content_type` | varchar(100) | sniffed and validated |
| `size_bytes` | integer | |
| `checksum_sha256` | varchar(64) | duplicate detection |
| `original_filename` | varchar(255) null | retained for display only |
| `created_at` | timestamptz | |

### `incident_status_history`

Append-only record of every transition.

| Column | Type |
|---|---|
| `id` | uuid PK |
| `incident_id` | uuid FK -> incidents, cascade, indexed |
| `from_status` | enum `incident_status` null (null on creation) |
| `to_status` | enum `incident_status` |
| `changed_by_id` | uuid null FK -> users |
| `note` | varchar(1000) null |
| `created_at` | timestamptz |

### `audit_logs`

| Column | Type |
|---|---|
| `id` | uuid PK |
| `actor_id` | uuid null FK -> users |
| `actor_role` | enum `user_role` null |
| `action` | varchar(80) — e.g. `incident.status_changed` |
| `entity_type` / `entity_id` | varchar(60) / varchar(80) |
| `ip_address` / `user_agent` | varchar null |
| `metadata` | jsonb null — never contains secrets |
| `created_at` | timestamptz, indexed |

Append-only: no update or delete path exists in application code.

## 3. Future tables (specified, not implemented)

### `incident_analyses` (Phase 6)

Stores AI output **separately from facts**.

```
id, incident_id, analysis_type (TEXT|IMAGE|AUDIO),
model_name, model_version, provider,
incident_type, severity, people_count, entities jsonb,
observations jsonb, confidence numeric(4,3),
reasoning_factors jsonb, raw_output jsonb,
reviewed_by_id, review_decision (ACCEPTED|EDITED|REJECTED), reviewed_at,
processing_ms, created_at
```

### `resources`, `ambulances`, `rescue_teams`, `hospitals`, `shelters` (Phase 10)

A shared `resources` supertype (code, type, home station, `geom`, status,
capabilities jsonb) with per-type detail tables. Resource status:
`AVAILABLE`, `ASSIGNED`, `EN_ROUTE`, `ON_SCENE`, `UNAVAILABLE`, `MAINTENANCE`.

### `resource_assignments`, `dispatches` (Phase 11)

Links incident to resource with `recommended_by` (engine/AI),
`approved_by_id` (**mandatory human**), timestamps for each lifecycle step,
and the distance/ETA at recommendation time.

### `notifications`, `alerts` (Phase 13)

Channel (`IN_APP`, `PUSH`, `SMS`, `EMAIL`), recipient, template, payload,
delivery state, provider message id.

### `roles`, `permissions`, `user_roles` (Phase 10)

Multi-role support; additive to the existing `users.role` column.

## 4. Entity relationships

```
users 1───* incidents           (reported_by)
users 1───* incidents           (assigned_to)
users 1───* refresh_tokens
incidents 1───* incident_media
incidents 1───* incident_status_history
incidents 1───* incident_analyses          (Phase 6)
incidents 1───* resource_assignments       (Phase 11)
resources 1───* resource_assignments       (Phase 11)
incidents 0..1───1 incidents               (duplicate_of)
```

## 5. Migration policy

- One Alembic revision per logical change; both `upgrade()` and `downgrade()`
  must be implemented and exercised locally.
- Enum values are added with `ALTER TYPE ... ADD VALUE` in a dedicated
  revision (Postgres cannot remove enum values — plan additively).
- No destructive migration without an explicit, reviewed data-migration step.
- Extensions (`postgis`) are created in the initial revision and are idempotent.

## 6. Data retention

| Data | Retention | Mechanism |
|---|---|---|
| Open incidents | Indefinite while open | — |
| Closed incidents | 24 months, then coarsened | Scheduled job (Phase 18) |
| Precise coordinates on closed incidents | 90 days, then truncated to ~1 km | Scheduled job |
| Media | 12 months after closure | Storage lifecycle rule |
| Audit logs | 36 months | Partition + archive |
| Refresh tokens | Purged 30 days after expiry | Scheduled job |

## 7. Seeds

`database/seeds/` holds synthetic development data only: one user per role and
a spread of incidents around the configured default map centre. Seed users use
an obvious development password and are refused when
`RAKSHA_ENVIRONMENT=production`.
