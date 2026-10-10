# RAKSHA NET AI — operations runbook

For the deployment architecture, see `docs/DEPLOYMENT.md`. This file is what an
on-call engineer opens at 3am.

---

## Health

| Check | Command |
|---|---|
| Liveness | `curl -fsS https://$HOST/api/v1/health` |
| Readiness | `curl -fsS https://$HOST/api/v1/health/ready` |

Readiness returns `503` when the database is unreachable. The orchestrator
should pull the instance from the load balancer rather than let it serve errors.

## Metrics

`GET /metrics` (Prometheus text) exists only when `RAKSHA_METRICS_TOKEN` is set,
and needs `Authorization: Bearer <token>`. It is outside `/api/v1`, so a proxy
that forwards only `/api/` does not expose it; scrape the backend directly on the
internal network.

```yaml
scrape_configs:
  - job_name: raksha
    metrics_path: /metrics
    authorization: { type: Bearer, credentials_file: /etc/prometheus/raksha-token }
    static_configs: [{ targets: ["backend:8000"] }]
```

Series worth alerting on (all `raksha_`-prefixed):

| Series | Meaning |
|---|---|
| `database_up` | 0 = a scrape could not query the database |
| `requests_shed_total` | rate > 0: the API is refusing requests (`503 SERVICE_BUSY`) |
| `requests_queued_total` | rising: requests are waiting for a slot — saturation is starting |
| `db_pool_exhausted_total` | rate > 0: requests are failing for want of a connection |
| `rate_limit_backend_errors_total` | rate > 0: Redis is failing; rate limits have fallen back to per-process counting |
| `db_pool_checked_out` vs `db_pool_size` | connections in use |
| `http_requests_total{status=~"5.."}` | error rate, by route template |
| `http_request_duration_seconds` | latency histogram, by route template |
| `incidents_open`, `incidents_unassigned_open` | queue depth |

Each API process reports on its own; scrape every process (or pod), not one.

## The API is slow, or returns SERVICE_BUSY

`503 SERVICE_BUSY` with `Retry-After` means the API is deliberately shedding load
(see `docs/PERFORMANCE.md`), not that it is down. It is distinct from a failing
readiness probe.

1. Look at `requests_queued_total`, `requests_shed_total` and
   `db_pool_checked_out`. Queued but not shed: a surge the API is absorbing.
   Shed: it is over capacity.
2. Add API processes (each can open up to `RAKSHA_DB_POOL_SIZE +
   RAKSHA_DB_MAX_OVERFLOW` connections — keep `processes x that` under PostgreSQL
   `max_connections`).
3. Do not raise `RAKSHA_MAX_CONCURRENT_REQUESTS` above the pool size to "fix" it:
   that brings back the deadlock the cap exists to prevent.

## The API is returning 503

1. Check readiness — it names the failing dependency.
2. If `database: unavailable`: check the managed instance's status, connection
   count and disk. A saturated connection pool looks identical from outside.
3. Check recent deploys. Roll back before debugging if a deploy correlates.
4. Reporting must keep working. If only AI is failing, confirm
   `RAKSHA_AI_ENABLED` can be set to `false` and restart — reporting and triage
   do not depend on it.

## Reports are being rejected with INVALID_COORDINATES

Almost always the operating bounding box. `RAKSHA_GEO_BBOX_*` defaults to India;
a deployment elsewhere must set it or every report outside that box is refused.
Verify with a known-good coordinate pair before changing anything.

## A user reports being signed out repeatedly

Refresh-token replay detection revokes an entire chain when a revoked token is
presented again. Legitimate causes:

- Two browser tabs racing a refresh. The shared client serialises this; an
  older cached bundle may not.
- A client retrying a failed refresh with the same token.

Check `audit_logs` for `auth.token_reuse_detected` for that user. Repeated
entries from one IP in a short window are a client bug; from different IPs,
treat as credential theft and force a password reset.

## Backing up

```bash
export POSTGRES_HOST=... POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
export BACKUP_AGE_RECIPIENT=age1...            # public key; see below
scripts/backup.sh --out /secure/backups --media /var/lib/raksha/media
```

Writes `raksha-<db>-<time>.dump[.age]` (PostgreSQL custom format) and a `.sha256`,
plus a media archive. **Encrypt backups**: a dump holds every report's text,
location and email in plaintext (only phone numbers and MFA secrets are
column-encrypted). With `BACKUP_AGE_RECIPIENT` set the backup host holds only the
public key and cannot read its own backups; keep the private key
(`BACKUP_AGE_IDENTITY`, used to restore) somewhere else. Without it the script
warns, and the backups must sit on storage that is itself encrypted and restricted.

**Also back up `RAKSHA_ENCRYPTION_KEY`, separately and securely.** It is not in the
dump, deliberately. Without it the encrypted phone numbers and every MFA secret
are unrecoverable, and every MFA user would need an administrator reset.

## Restoring the database

```bash
# Restore into a NEW database. It never overwrites unless you pass --drop-existing.
export BACKUP_AGE_IDENTITY=/secure/age-private-key.txt     # only for *.age
export RAKSHA_ENCRYPTION_KEY=...                            # the SAME key as the source
scripts/restore.sh --file /secure/backups/raksha-raksha_net_ai-...dump.age \
    --target-db raksha_net_ai_restored \
    --media-archive /secure/backups/raksha-media-...tar.gz.age --media-dir /var/lib/raksha/media
```

It checks the file against its `.sha256` first, validates its inputs before
creating anything, and removes the new database if the restore fails part-way, so
an incomplete restore cannot be mistaken for a result.

Then, **before reopening traffic**:

```bash
psql -d raksha_net_ai_restored -c "SELECT postgis_version();"
cd backend && POSTGRES_DB=raksha_net_ai_restored alembic current   # must match the deployed revision
# Point the application at the restored database, start it, and confirm
# /api/v1/health/ready, then reopen traffic.
```

### Prove it works: `scripts/verify_restore.sh`

```bash
scripts/verify_restore.sh --db raksha_net_ai
```

Backs the database up, restores it into a scratch database, and fails unless every
table's row count, the incident ids (as a checksum), the schema revision, the
indexes, a spatial query and the decryption of the encrypted columns all agree.
Run it against a quiet database or a replica (a write between the dump and the
comparison is a real difference). **Rehearse quarterly, from your real backups, in
an isolated environment** — the script proves the procedure and the tooling, not
that last night's backup is good.

### What this does and does not establish

- Verified here: the scripts, on a 100,000-incident / 70,000-dispatch database
  (83 MB): backup 3 s, restore 4 s, all comparisons pass; corruption, a wrong
  private key, a wrong encryption key and an existing target are each refused; an
  encrypted backup is not a readable dump; media files restore byte-for-byte.
  That is a development machine and a small database, so treat the seconds as a
  floor, not an RTO.
- **Not established: the 15-minute RPO.** A logical dump's RPO is the interval
  between backups. 15 minutes needs continuous WAL archiving / point-in-time
  recovery on the database platform (a managed PostgreSQL feature); that is
  infrastructure, and nothing here proves it. Until it exists, state the RPO as
  your backup interval.
- **Not established: the 1-hour RTO** on production-sized data and hardware.
- A restore into a real production environment has not been rehearsed.

## Rotating the signing key

Rotating `RAKSHA_SECRET_KEY` invalidates access tokens within their 30-minute
TTL. Refresh tokens survive, because they are opaque random values stored as
hashes rather than signed — so a rotation does not sign everyone out.

## Rotating the encryption key

`RAKSHA_ENCRYPTION_KEY` protects contact numbers and MFA secrets at rest. It is
independent of `RAKSHA_SECRET_KEY`, so the two rotate separately.

1. Generate a new key (see `.env.example`).
2. Set `RAKSHA_ENCRYPTION_KEY=<new>,<old>` and redeploy. New writes use the
   first key; every existing value still decrypts with the second.
3. Existing rows are re-encrypted lazily, only when next written. To force it,
   re-save them; there is no bulk re-encryption job yet.
4. Only when no row still depends on `<old>` may it be dropped. **Dropping it
   early makes those values unreadable and the application will raise on them
   rather than show garbage.** Back up before step 4.

Losing the key loses the data in those columns. Keep it in the secret manager,
never in the repository or beside the database backups.

## Someone is locked out

- **Locked by failed sign-ins** (`403 ACCOUNT_LOCKED`; the response says how
  long): wait, or an administrator calls `POST /api/v1/users/{id}/unlock`.
  Repeated locks of the same account from unfamiliar addresses are worth a look
  in `audit_logs` (`auth.account_locked`) — it may be someone locking a
  dispatcher out on purpose.
- **Lost or replaced phone (MFA)**: an administrator calls
  `POST /api/v1/users/{id}/reset-mfa`. This also ends that user's sessions. The
  user then enrols again. An administrator cannot reset their own; if the only
  administrator loses their device, another administrator (or the database) is
  the only way back — there are no recovery codes.
- Verify the person first. An MFA reset is a password-only account for as long
  as it takes them to re-enrol.

## Malware scanning

Run a ClamAV daemon reachable from the API and set `RAKSHA_CLAMAV_HOST`. Until
then uploads are stored as `UNSCANNED`: the field is visible on every file and
means no scan happened. Decide deliberately whether an unreachable scanner should
refuse uploads (`RAKSHA_CLAMAV_REQUIRED=true`) or keep them as `UNSCANNED` (the
default, so an outage in an optional tool cannot stop a report being completed).
The scanner client has been tested against a stand-in daemon only; confirm it
against your ClamAV (send the EICAR test string) before relying on it.

## Suspected compromise of an operator account

1. `PATCH /api/v1/users/{id}` with `{"is_active": false}`. Access is checked
   against the database on every request, so this takes effect immediately
   rather than at token expiry.
2. Query `audit_logs` for that `actor_id` to scope what was touched.
3. Review every `incident.priority_overridden` and `incident.status_changed`
   entry by that actor.
4. Reset credentials before reactivating.

## Escalation

| Condition | Action |
|---|---|
| Reporting path down > 5 min | Page the on-call engineer; notify the operating authority |
| Data loss suspected | Stop writes, preserve WAL, escalate before restoring |
| Security incident | Follow the organisation's incident-response policy; preserve `audit_logs` |
