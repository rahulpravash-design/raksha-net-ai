#!/usr/bin/env bash
# Run the full quality gate, exactly as CI does.
#
#   ./scripts/check.sh
#
# Every check runs even if an earlier one fails, so one pass shows every
# problem rather than only the first.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAILURES=()

run() {
  local name="$1"; shift
  echo ""
  echo "==> $name"
  if "$@"; then
    echo "    ok"
  else
    echo "    FAILED"
    FAILURES+=("$name")
  fi
}

run "backend: ruff"       backend/.venv/bin/ruff check backend
run "backend: black"      backend/.venv/bin/black --check backend
run "backend: mypy"       bash -c "cd backend && .venv/bin/mypy app"
run "backend: pytest"     bash -c "cd backend && .venv/bin/pytest -q"
run "ai: pytest"          bash -c "PYTHONPATH=. backend/.venv/bin/pytest ai/tests -q"

for app in citizen-web control-center; do
  run "$app: eslint"    npm run lint --silent --workspace "@raksha/$app"
  run "$app: tsc"       npm run typecheck --silent --workspace "@raksha/$app"
  run "$app: vitest"    npm run test --silent --workspace "@raksha/$app"
  run "$app: build"     npm run build --silent --workspace "@raksha/$app"
done

echo ""
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "All checks passed."
  exit 0
fi

echo "Failed: ${FAILURES[*]}"
exit 1
