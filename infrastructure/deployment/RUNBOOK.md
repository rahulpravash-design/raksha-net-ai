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
