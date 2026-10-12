#!/usr/bin/env bash
# Prove a backup can be restored, by doing it.
#
#   scripts/verify_restore.sh [--db NAME] [--keep]
#
# Backs the database up, restores that backup into a scratch database, and
# compares the two. It fails (exit 1) unless ALL of these hold:
#
#   * every table has the same row count
#   * the incident ids match (a checksum, not just a count)
#   * the schema revision matches
#   * the set of indexes matches
#   * a spatial radius query returns the same rows
#   * every encrypted contact number can still be decrypted
#
# Run it against a QUIET database (or a replica): a write landing between the dump
# and the comparison is a genuine difference and will fail the check.
#
# It needs the application's environment — the same RAKSHA_ENCRYPTION_KEY (or, in
# development, RAKSHA_SECRET_KEY) the source uses — and BACKUP_AGE_RECIPIENT +
# BACKUP_AGE_IDENTITY to exercise the encrypted path. The numbers it prints
# (sizes, seconds) are a guide to recovery time on THIS machine, not a measured RTO.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/_pg.sh
. "$REPO_ROOT/scripts/_pg.sh"

DB="$SOURCE_DB"; KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --db) DB="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
need psql
PY="$REPO_ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

SCRATCH="${DB}_verify"
WORK="$(mktemp -d)"
cleanup() {
  rm -rf "$WORK"
  if [ "$KEEP" -eq 0 ]; then
    psql -X -q -d postgres -c "DROP DATABASE IF EXISTS \"$SCRATCH\" WITH (FORCE)" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

src() { psql -X -qAt -d "$DB" -c "$1"; }
dst() { psql -X -qAt -d "$SCRATCH" -c "$1"; }

FAILED=0
check() {  # name, expected, actual
  if [ "$2" = "$3" ]; then echo "  PASS  $1"; else
    echo "  FAIL  $1"; echo "          source : $2"; echo "          restored: $3"; FAILED=1
  fi
}

echo "== backup '$DB'"
T0="$(now_s)"
"$REPO_ROOT/scripts/backup.sh" --db "$DB" --out "$WORK" 2>&1 | sed 's/^/   /'
FILE="$(ls "$WORK"/raksha-"$DB"-*.dump* | grep -v '\.sha256$' | head -1)"
T1="$(now_s)"

echo "== restore into '$SCRATCH'"
"$REPO_ROOT/scripts/restore.sh" --file "$FILE" --target-db "$SCRATCH" --drop-existing 2>&1 | sed 's/^/   /'
T2="$(now_s)"

echo "== compare"
tables="$(src "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")"
for t in $tables; do
  check "rows in $t" "$(src "SELECT count(*) FROM \"$t\"")" "$(dst "SELECT count(*) FROM \"$t\"")"
done
check "incident ids" \
  "$(src "SELECT md5(coalesce(string_agg(id::text, ',' ORDER BY id), '')) FROM incidents")" \
  "$(dst "SELECT md5(coalesce(string_agg(id::text, ',' ORDER BY id), '')) FROM incidents")"
check "schema revision" \
  "$(src "SELECT version_num FROM alembic_version")" "$(dst "SELECT version_num FROM alembic_version")"
check "indexes" \
  "$(src "SELECT string_agg(indexname, ',' ORDER BY indexname) FROM pg_indexes WHERE schemaname='public'")" \
  "$(dst "SELECT string_agg(indexname, ',' ORDER BY indexname) FROM pg_indexes WHERE schemaname='public'")"
RADIUS="SELECT count(*) FROM incidents WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(80.25, 13.05), 4326)::geography, 5000)"
check "spatial query (5 km radius)" "$(src "$RADIUS")" "$(dst "$RADIUS")"

DECRYPT_CHECK='
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_engine
from app.models import Hospital, Incident, Resource

checked = 0
with Session(get_engine()) as session:
    for model in (Incident, Resource, Hospital):
        stmt = select(model).where(model.contact_phone.is_not(None)).limit(50)
        for row in session.scalars(stmt):
            assert row.contact_phone  # reading it decrypts; a wrong key raises
            checked += 1
print(checked)
'
if decrypted="$(cd "$REPO_ROOT/backend" && POSTGRES_DB="$SCRATCH" PYTHONPATH="$REPO_ROOT/backend:$REPO_ROOT" "$PY" -c "$DECRYPT_CHECK" 2>&1)"; then
  if [ "$decrypted" = "0" ]; then
    echo "  WARN  no encrypted contact numbers exist, so decryption was NOT exercised"
  else
    echo "  PASS  $decrypted encrypted contact numbers decrypt after restore"
  fi
else
  echo "  FAIL  encrypted columns could not be read after restore (wrong RAKSHA_ENCRYPTION_KEY?)"
  echo "$decrypted" | tail -3 | sed 's/^/          /'
  FAILED=1
fi
T3="$(now_s)"

echo "== timing (this machine, this size — not an RTO)"
echo "   backup $((T1 - T0)) s   restore $((T2 - T1)) s   verify $((T3 - T2)) s"
echo "   source $(src "SELECT pg_size_pretty(pg_database_size('$DB'))")  backup file $(du -h "$FILE" | cut -f1)"

if [ "$FAILED" -ne 0 ]; then echo "RESTORE VERIFICATION FAILED"; exit 1; fi
echo "restore verified"
