#!/usr/bin/env bash
# Apply database migrations.
#
#   ./scripts/migrate.sh              # upgrade to head
#   ./scripts/migrate.sh downgrade -1 # roll back one revision
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

if [ $# -eq 0 ]; then
  exec .venv/bin/alembic upgrade head
fi
exec .venv/bin/alembic "$@"
