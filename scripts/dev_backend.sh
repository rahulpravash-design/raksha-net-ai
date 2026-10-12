#!/usr/bin/env bash
# Run the API with reload, for local development.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

export PYTHONPATH="$REPO_ROOT/backend:$REPO_ROOT"
exec .venv/bin/uvicorn app.main:app --reload --port "${PORT:-8000}"
