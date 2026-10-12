# Shared by backup.sh, restore.sh and verify_restore.sh: map the application's
# POSTGRES_* settings onto libpq's PG* variables. Sourced, not executed.

export PGHOST="${POSTGRES_HOST:-localhost}"
export PGPORT="${POSTGRES_PORT:-5432}"
export PGUSER="${POSTGRES_USER:-raksha}"
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
fi
SOURCE_DB="${POSTGRES_DB:-raksha_net_ai}"

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed"; }
now_s() { date +%s; }
