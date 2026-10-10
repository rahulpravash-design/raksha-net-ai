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

## Restoring the database

RPO 15 minutes, RTO 1 hour.

```bash
# 1. Stop the application so nothing writes during the restore.
# 2. Restore the latest base backup, then replay WAL to the target time.
# 3. Verify before reopening traffic:
psql -d raksha_net_ai -c "SELECT postgis_version();"
psql -d raksha_net_ai -c "SELECT count(*) FROM incidents WHERE status NOT IN ('CLOSED','CANCELLED','DUPLICATE','REJECTED');"
cd backend && alembic current     # must match the deployed revision
# 4. Start the application. Confirm readiness, then reopen traffic.
```

A backup that has never been restored is not a backup. Rehearse quarterly into
an isolated environment.

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
