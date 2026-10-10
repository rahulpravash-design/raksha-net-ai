# RAKSHA NET AI — Releasing and rolling back

A procedure, not a pipeline. **There is no continuous-deployment system in this
repository**: CI builds, tests, audits and checks migrations (`.github/workflows/ci.yml`),
and nothing publishes an image or deploys it. Everything below is done by a person.
Writing it down is not the same as having rehearsed it in a real environment, and
it has not been.

## Order, always

**Migrate, then release.** Readiness enforces half of this: an instance whose
database schema is *behind* its code reports `503` with `schema_state: behind`
(`GET /api/v1/health/ready`), so the orchestrator will not route traffic to it
until the migration has run. It also protects the container health check, which
calls the same endpoint.

`schema_state` is `current`, `behind` (not ready), `ahead` (the database holds a
revision this code does not know — normal right after rolling the application
back) or `unknown` (no recorded revision, as in a fresh or `create_all` database).

## Before a release

1. `./scripts/check.sh` is green (includes migrations apply/roll back, drift
   check, dependency audits, all tests). Read its last line.
2. **Take a backup and verify it** — `scripts/backup.sh`, then restore it into a
   scratch database (`scripts/verify_restore.sh`). Do this *before* migrating.
3. Confirm `RAKSHA_ENCRYPTION_KEY` is available to the new version, unchanged.
4. Read the migrations in the release. Classify each (below).
5. For any migration that rewrites data, rehearse the upgrade **and** downgrade on
   a restored copy of production, not only on an empty database. The gate proves
   the chain on empty tables only.

## Releasing

```bash
cd backend
alembic current                      # confirm where you are
alembic upgrade head                 # migrate first
# then roll out the new application version, one instance at a time
curl -fsS https://$HOST/api/v1/health/ready      # expect "schema_state": "current"
```

Watch `raksha_http_requests_total{status=~"5.."}`, `raksha_requests_shed_total`
and `raksha_db_pool_exhausted_total` (see the runbook) for the first minutes.

## Rolling back

Decide by what the release's migrations did.

### Roll back the application only (safe)

Migrations **0009** (lockout columns), **0011** (MFA columns), **0012** (upload
scan status) and **0013** (an index) are *additive*: the new columns are nullable
or carry server defaults, so the previous application version runs against the
newer schema, and the database does not need to move. Readiness will show
`schema_state: ahead`, which is expected.

Checked, not assumed: the application models from before Phase 16 were run
against a database migrated to 0013. Inserting a user and an upload succeeded and
the new columns took their defaults (`failed_login_attempts` 0, `mfa_enabled`
false, `scan_status` `UNSCANNED`). That is a model-level check on one database,
not a rehearsed rollback.

### Rolling back past 0010 needs the database to move first

**0010 encrypts contact numbers in place.** The previous application version
would read ciphertext as phone numbers and write plaintext into the widened
columns. So:

```bash
# with RAKSHA_ENCRYPTION_KEY set to the key the data was encrypted with
alembic downgrade 0009_account_lockout     # decrypts in place, narrows the columns
# then deploy the older application
```

Take a backup first. Without the key the downgrade cannot decrypt, and the numbers
are lost.

### Downgrades that destroy data

| Downgrade of | Loses |
|---|---|
| 0012 | the per-file `scan_status` |
| 0011 | every user's MFA secret and enrolment (everyone must re-enrol) |
| 0010 | nothing, if the key is right; **the numbers** if it is not |
| 0009 | lockout counters (harmless) |

None of them needs to run just to roll the *application* back past 0011 or 0012;
the old code ignores the extra columns. Prefer leaving the schema alone.

### If the migration itself failed

Migrations run in a transaction (PostgreSQL DDL is transactional), so a failed
`alembic upgrade` leaves the previous revision in place. Fix forward or restore
the pre-release backup into a new database (runbook) — do not hand-edit
`alembic_version`.

## What is not covered

- No automated image build, registry, deploy, canary or automatic rollback.
- No blue/green or zero-downtime guarantee; a rolling deploy relies on readiness.
- The expand/contract discipline in `DEPLOYMENT.md` §5 is a rule for authors, not
  something the gate enforces.
