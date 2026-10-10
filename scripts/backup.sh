#!/usr/bin/env bash
# Back up the database (and optionally the media files).
#
#   scripts/backup.sh [--db NAME] [--out DIR] [--media DIR]
#
# Uses the same POSTGRES_* environment as the application.
#
#   BACKUP_AGE_RECIPIENT   an `age` public key. When set, the backup is encrypted
#                          to it. The machine making backups then holds only the
#                          PUBLIC key and cannot read them back; keep the private
#                          key (BACKUP_AGE_IDENTITY, used by restore.sh) elsewhere.
#
# A dump holds every report's text, location and email in plaintext — only the
# phone numbers and MFA secrets are encrypted at the column level — so an
# unencrypted backup must live on storage that is itself encrypted and restricted.
# This script says so when you do not encrypt.
#
# Encrypted columns need RAKSHA_ENCRYPTION_KEY at restore time. It is NOT in the
# backup, deliberately; losing it makes those columns unreadable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/_pg.sh
. "$REPO_ROOT/scripts/_pg.sh"

DB="$SOURCE_DB"; OUT="${BACKUP_DIR:-$REPO_ROOT/backups}"; MEDIA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --db) DB="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --media) MEDIA="$2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

need pg_dump
umask 077
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="$OUT/raksha-$DB-$STAMP"
STARTED="$(now_s)"

if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  need age
  FILE="$BASE.dump.age"
  pg_dump --format=custom --no-owner --no-privileges --dbname="$DB" \
    | age --recipient "$BACKUP_AGE_RECIPIENT" > "$FILE"
else
  FILE="$BASE.dump"
  echo "WARNING: writing an UNENCRYPTED backup. It contains report text, locations" >&2
  echo "         and emails in plaintext. Set BACKUP_AGE_RECIPIENT to encrypt it." >&2
  pg_dump --format=custom --no-owner --no-privileges --dbname="$DB" --file="$FILE"
fi
( cd "$OUT" && sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256" )
echo "database : $FILE ($(du -h "$FILE" | cut -f1))"

if [ -n "$MEDIA" ]; then
  [ -d "$MEDIA" ] || die "media directory not found: $MEDIA"
  MFILE="$OUT/raksha-media-$STAMP.tar.gz"
  if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
    MFILE="$MFILE.age"
    tar -C "$MEDIA" -czf - . | age --recipient "$BACKUP_AGE_RECIPIENT" > "$MFILE"
  else
    tar -C "$MEDIA" -czf "$MFILE" .
  fi
  ( cd "$OUT" && sha256sum "$(basename "$MFILE")" > "$(basename "$MFILE").sha256" )
  echo "media    : $MFILE ($(du -h "$MFILE" | cut -f1))"
fi
echo "took $(( $(now_s) - STARTED )) s"
