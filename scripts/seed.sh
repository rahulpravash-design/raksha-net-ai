#!/usr/bin/env bash
# Load synthetic development data.
#
#   ./scripts/seed.sh            # add seed data
#   ./scripts/seed.sh --reset    # clear seeded data first
#
# Refuses to run against a staging or production environment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

exec backend/.venv/bin/python database/seeds/seed_development.py "$@"
