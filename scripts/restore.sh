#!/usr/bin/env bash
# Restore a backup made by backup.sh into a NEW database.
#
#   scripts/restore.sh --file BACKUP --target-db NAME [--drop-existing]
#                      [--media-archive FILE --media-dir DIR]
#
#   BACKUP_AGE_IDENTITY   path to the `age` private key, needed for *.age files.
#
# It never restores over an existing database unless you pass --drop-existing,
# and it checks the file against its .sha256 first. To recover production, restore
# into a fresh database, verify it (scripts/verify_restore.sh does this for you),
# then point the application at it.
#
# Set RAKSHA_ENCRYPTION_KEY to the SAME key the source used, or the encrypted
# columns will not be readable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/_pg.sh
. "$REPO_ROOT/scripts/_pg.sh"

FILE=""; TARGET=""; DROP=0; MARCHIVE=""; MDIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file) FILE="$2"; shift 2 ;;
    --target-db) TARGET="$2"; shift 2 ;;
    --drop-existing) DROP=1; shift ;;
    --media-archive) MARCHIVE="$2"; shift 2 ;;
    --media-dir) MDIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ -n "$FILE" ] && [ -n "$TARGET" ] || die "--file and --target-db are required"
[ -f "$FILE" ] || die "backup not found: $FILE"
need pg_restore; need psql

verify_checksum() {
  local f="$1"
  if [ -f "$f.sha256" ]; then
    ( cd "$(dirname "$f")" && sha256sum --check --quiet "$(basename "$f").sha256" ) \
      || die "checksum mismatch for $f — the file is corrupt or has been altered"
  else
    echo "WARNING: no .sha256 beside $f; integrity not checked" >&2
  fi
}

# Everything that can be checked without touching the server is checked first,
# so a bad invocation cannot leave a half-made database behind.
if [[ "$FILE" == *.age ]]; then
  need age
  [ -n "${BACKUP_AGE_IDENTITY:-}" ] || die "BACKUP_AGE_IDENTITY must point at the age private key"
  [ -f "$BACKUP_AGE_IDENTITY" ] || die "age identity file not found: $BACKUP_AGE_IDENTITY"
fi
if [ -n "$MARCHIVE" ]; then
  [ -n "$MDIR" ] || die "--media-dir is required with --media-archive"
  [ -f "$MARCHIVE" ] || die "media archive not found: $MARCHIVE"
  if [[ "$MARCHIVE" == *.age ]]; then
    need age; [ -n "${BACKUP_AGE_IDENTITY:-}" ] || die "BACKUP_AGE_IDENTITY is needed for the media archive"
  fi
fi

STARTED="$(now_s)"
verify_checksum "$FILE"
[ -z "$MARCHIVE" ] || verify_checksum "$MARCHIVE"

exists="$(psql -X -qAt -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")"
if [ -n "$exists" ]; then
  [ "$DROP" -eq 1 ] || die "database '$TARGET' already exists; pass --drop-existing to replace it"
  psql -X -q -d postgres -c "DROP DATABASE \"$TARGET\" WITH (FORCE)"
fi
psql -X -q -d postgres -c "CREATE DATABASE \"$TARGET\""

# From here a failure leaves a database that is empty or half-restored, which
# looks like a result. Remove it unless the restore completed.
COMPLETED=0
cleanup_incomplete() {
  if [ "$COMPLETED" -ne 1 ]; then
    echo "restore did not complete; removing the incomplete database '$TARGET'" >&2
    psql -X -q -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET\" WITH (FORCE)" >/dev/null 2>&1 || true
  fi
}
trap cleanup_incomplete EXIT

if [[ "$FILE" == *.age ]]; then
  age --decrypt --identity "$BACKUP_AGE_IDENTITY" "$FILE" \
    | pg_restore --exit-on-error --no-owner --no-privileges --dbname="$TARGET"
else
  pg_restore --exit-on-error --no-owner --no-privileges --dbname="$TARGET" "$FILE"
fi
COMPLETED=1
echo "database restored into '$TARGET' in $(( $(now_s) - STARTED )) s"

if [ -n "$MARCHIVE" ]; then
  mkdir -p "$MDIR"
  if [[ "$MARCHIVE" == *.age ]]; then
    age --decrypt --identity "$BACKUP_AGE_IDENTITY" "$MARCHIVE" | tar -C "$MDIR" -xzf -
  else
    tar -C "$MDIR" -xzf "$MARCHIVE"
  fi
  echo "media restored into $MDIR"
fi
