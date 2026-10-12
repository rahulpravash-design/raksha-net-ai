#!/bin/sh
# Start command for a host without a shell or a pre-deploy step (Render's free tier).
# See docs/DEPLOYMENT.md 13.3 and 13.7.
#
#  1. Apply the migrations. Run one instance only: two starting at once would race.
#  2. If FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD are set, create the first super
#     administrator. With --skip-if-admin-exists every later boot does nothing. The
#     password reaches the command on standard input from a shell builtin, so it never
#     shows in a process listing, and it is removed from the environment before the API
#     starts. Delete both variables on the host after the first successful boot.
#  3. Serve on the port the platform assigns ($PORT), or 8000.
set -eu

alembic upgrade head

if [ -n "${FIRST_ADMIN_EMAIL:-}" ] && [ -n "${FIRST_ADMIN_PASSWORD:-}" ]; then
    # A bootstrap problem (a weak password, say) must not take the API down with it:
    # report it loudly and carry on serving.
    if printf '%s\n' "$FIRST_ADMIN_PASSWORD" | python -m app.cli.create_first_admin \
        --email "$FIRST_ADMIN_EMAIL" \
        --name "${FIRST_ADMIN_NAME:-Administrator}" \
        --password-stdin --skip-if-admin-exists; then
        :
    else
        echo "render_start: the first administrator was NOT created (exit $?); see above." >&2
    fi
fi
unset FIRST_ADMIN_PASSWORD

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
