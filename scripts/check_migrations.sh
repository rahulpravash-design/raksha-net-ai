#!/usr/bin/env bash
# Prove the migration chain is sound, and that it matches the models.
#
#   ./scripts/check_migrations.sh
#
# Runs against the *test* database (the one pytest already needs), which is
# empty between test runs: upgrade to head, fail if the models and migrations
# disagree (`alembic check`), then downgrade to base so the whole chain is
# shown to reverse. Needs the same POSTGRES_* environment as the test suite.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

ALEMBIC_DATABASE_URL="$(.venv/bin/python -c "
from app.core.config import get_settings
s = get_settings()
base = s.sqlalchemy_database_uri
print(s.test_database_url or (base if base.endswith('_test') else base + '_test'))
")"
export ALEMBIC_DATABASE_URL

.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/alembic downgrade base
