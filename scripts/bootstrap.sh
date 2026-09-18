#!/usr/bin/env bash
# Prepare a local development environment from a fresh checkout.
#
#   ./scripts/bootstrap.sh
#
# Idempotent: safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Checking prerequisites"
for tool in python3 node npm; do
  command -v "$tool" >/dev/null || { echo "Missing: $tool"; exit 1; }
done

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  # A generated secret beats a placeholder someone forgets to replace.
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  python3 - "$SECRET" <<'PY'
import pathlib, sys
p = pathlib.Path(".env")
p.write_text(
    p.read_text().replace(
        "RAKSHA_SECRET_KEY=generate_a_unique_64_byte_secret_before_running",
        f"RAKSHA_SECRET_KEY={sys.argv[1]}",
    )
)
PY
  echo "    Generated RAKSHA_SECRET_KEY. Set POSTGRES_PASSWORD before starting."
else
  echo "==> .env already exists, leaving it alone"
fi

echo "==> Creating the backend virtual environment"
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -r backend/requirements-dev.txt

echo "==> Installing frontend dependencies"
npm install --no-audit --no-fund

cat <<'NEXT'

Bootstrap complete.

  1. Edit .env and set POSTGRES_PASSWORD.
  2. Start PostgreSQL and Redis:   docker compose up -d db redis
  3. Apply migrations:             ./scripts/migrate.sh
  4. Seed development data:        ./scripts/seed.sh
  5. Run the backend:              ./scripts/dev_backend.sh
  6. Run the front ends:           npm run dev:citizen   (and dev:control)

NEXT
