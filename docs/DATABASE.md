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
| `failed_login_attempts` | integer, default 0 | consecutive failures since the last success (Phase 16) |
| `locked_until` | timestamptz null | set when the threshold is reached; refused until it passes |
| `mfa_enabled` | boolean, default false | TOTP second factor is active |
| `must_change_password` | boolean, default false | An administrator chose this password; it must be replaced before anything else works (migration 0014) |
| `mfa_secret` | varchar(255) null | TOTP shared secret, **encrypted at rest** (Fernet); present while enrolment is pending and once enabled |
| `mfa_last_step` | bigint null | 30-second step of the last accepted code, to refuse a replay |
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
| `scan_status` | enum `scan_status` | `CLEAN` or `UNSCANNED`. `UNSCANNED` means no scan happened, never "safe". Existing rows are `UNSCANNED`. (Phase 16) |
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

## 3. Tables added after V1 (implemented)

Column lists below are read from the migrated schema. A trailing `?` means
nullable; every table also has `id` and timestamps.

| Table | Phase | Columns | Notes |
|---|---|---|---|
| `incident_analyses` | 6 | `incident_id`, `model_name`, `model_version`, `provider?`, `processing_ms?`, `proposed_category?`, `type_confidence?`, `proposed_severity?`, `severity_confidence?`, `people_affected?`, `people_trapped?`, `medical_support_required?`, `immediate_rescue_required?`, `entities`, `observations`, `reasoning_factors`, `review_decision?`, `reviewed_by_id?`, `reviewed_at?`, `review_note?`, `applied_fields?` | AI output, stored apart from `incidents`. `review_decision IS NULL` means pending. |
| `voice_transcripts` | 9 | `reporter_id`, `incident_id?` (unique; set when the report is sent), `linked_at?`, `reporter_edited?`, `text`, `confidence`, `language?`, `language_hint?`, `duration_seconds?`, `model_name`, `model_version`, `provider`, `processing_ms`, `audio_content_type`, `audio_size_bytes` | What a speech model heard in a reporter's dictation: AI-derived, apart from `incidents`. **No column holds the recording** — it is never stored. Unlinked rows older than a day are removed the next time anyone dictates (no scheduled job yet; see section 6). |
| `resources` | 10 | `call_sign` (unique), `name`, `resource_type`, `status`, `latitude`, `longitude`, `geom` (GIST), `base_address?`, `capabilities` (jsonb), `crew_size?`, `contact_phone?` (**encrypted**), `operator_id?`, `is_active`, `status_changed_at?` | |
| `dispatches` | 11 | `incident_id`, `resource_id`, `approved_by_id` (**NOT NULL**), `status`, `distance_km?`, `estimated_minutes?`, `note?`, `cancel_reason?`, `acknowledged_at?`, `en_route_at?`, `on_scene_at?`, `closed_at?` | The NOT NULL approver is the schema-level guarantee that no dispatch exists without a named human. |
| `hospitals` | 12 | `code` (unique), `name`, `latitude`, `longitude`, `geom` (GIST), `address?`, `contact_phone?` (**encrypted**), `total_beds`, `available_beds`, `icu_total`, `icu_available`, `accepting_emergencies`, `specialties` (jsonb), `managed_by_id?`, `is_active`, `capacity_updated_at?` | CHECKs keep available <= total. |
| `inbound_patient_notices` | 12 | `hospital_id`, `incident_id`, `dispatch_id?`, `created_by_id`, `status`, `patient_count`, `category`, `severity?`, `eta_minutes?`, `clinical_notes?`, `response_note?`, `acknowledged_at?`, `closed_at?` | Deliberately has no reporter, contact, description or coordinate column. |
| `notifications` | 13 | `user_id`, `kind`, `title`, `body`, `incident_id?`, `dispatch_id?`, `context?`, `read_at?` | |
| `notification_deliveries` | 13 | `notification_id`, `channel`, `status`, `attempts`, `detail?`, `delivered_at?` | One row per channel attempted; `UNAVAILABLE` records an unconfigured channel. |

`incidents` also gained `priority_engine_version` (Phase 7), recording which
configuration produced each score; it is null for rows scored before Phase 7.

### Encryption at rest

`incidents.contact_phone`, `resources.contact_phone`, `hospitals.contact_phone`
and `users.mfa_secret` hold Fernet ciphertext (`gAAAA…`, about 100 characters
for a phone number). The ORM encrypts and decrypts transparently
(`app/db/types.py`); anything that reads these columns with raw SQL must call
`app.core.crypto.decrypt_value` itself. `users.phone` is **not** encrypted: it
is unique and looked up, and randomised ciphertext supports neither.

### Not yet specified in migrations

`roles` / `permissions` / `user_roles` (multi-role support) and `alerts` remain
unbuilt. `resource_assignments` was not needed: `dispatches` is the assignment.

---

## 4. Entity relationships

```
users 1───* incidents           (reported_by)
users 1───* incidents           (assigned_to)
users 1───* refresh_tokens
incidents 1───* incident_media
incidents 1───* incident_status_history
incidents 1───* incident_analyses          (Phase 6)
incidents 1───? voice_transcripts          (Phase 9)
users     1───* voice_transcripts          (Phase 9, reporter)
incidents 1───* dispatches                 (Phase 11)
resources 1───* dispatches                 (Phase 11)
hospitals 1───* inbound_patient_notices    (Phase 12)
incidents 1───* inbound_patient_notices    (Phase 12)
users     1───* notifications              (Phase 13)
notifications 1───* notification_deliveries (Phase 13)
incidents 0..1───1 incidents               (duplicate_of)
```

## 5. Migration policy

- One Alembic revision per logical change; both `upgrade()` and `downgrade()`
  must be implemented and exercised locally.
- Enum values are added with `ALTER TYPE ... ADD VALUE` in a dedicated
  revision (Postgres cannot remove enum values — plan additively).
- No destructive migration without an explicit, reviewed data-migration step.
- Extensions (`postgis`) are created in the initial revision and are idempotent.
- `scripts/check_migrations.sh` runs in the gate: it upgrades an empty database
  to head, fails if models and migrations disagree (`alembic check`), then
  downgrades to base. A model change without a migration fails the build.
- The drift check ignores tables and views that an installed extension owns
  (`migrations/env.py`). The `postgis/postgis` image used by CI and
  docker-compose also installs the topology and TIGER geocoder extensions and
  puts their schemas on the search path, so without the filter their tables
  read as tables the models dropped. Only objects present in the database and
  absent from the models are skipped; every other difference still fails.
- A migration that rewrites data (`0010`, which encrypts existing contact
  numbers) must be re-runnable and must reverse cleanly; it skips a value
  already in the target form.

Current chain: `0001_enable_postgis` -> `0002_create_core_schema` ->
`0003_incident_analyses` -> `0004_priority_engine_version` -> `0005_resources`
-> `0006_dispatches` -> `0007_hospitals` -> `0008_notifications` ->
`0009_account_lockout` -> `0010_encrypt_contact_details` -> `0011_mfa` ->
`0012_media_scan_status` -> `0013_incident_created_at_index` -> `0014_must_change_password`
-> `0015_password_reset_tokens` -> `0016_mfa_recovery_codes` -> `0017_voice_transcripts`.

## 6. Data retention

| Data | Retention | Mechanism |
|---|---|---|
| Open incidents | Indefinite while open | — |
| Closed incidents | 24 months, then coarsened | Scheduled job (Phase 18) |
| Precise coordinates on closed incidents | 90 days, then truncated to ~1 km | Scheduled job |
| Media | 12 months after closure | Storage lifecycle rule |
| Audit logs | 36 months | Partition + archive |
| Refresh tokens | Purged 30 days after expiry | Scheduled job |
| Voice transcripts never sent with a report | 24 hours | **Opportunistic only:** purged inside `POST /transcriptions` the next time anyone dictates. No scheduler exists yet, so one can outlive its day if nobody dictates afterwards; a scheduled job (Phase 18) would make this a guarantee |

## 7. Seeds

`database/seeds/` holds synthetic development data only: one user per role and
a spread of incidents around the configured default map centre. Seed users use
an obvious development password and are refused when
`RAKSHA_ENVIRONMENT=production`.
