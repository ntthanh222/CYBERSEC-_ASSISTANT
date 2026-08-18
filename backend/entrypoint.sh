#!/bin/sh
# POSIX sh, not bash: the runtime image drops bash (and everything that
# pulls in libtinfo6/ncurses transitively) to close out Trivy findings with
# no fixed version upstream - dash (Debian's /bin/sh) has no such
# dependency. No `pipefail` (dash doesn't support it) - this script has no
# pipes, so it was never functionally needed, only bash's default posture.
set -eu

cd /app/backend

attempt=1
max_attempts=5
until alembic upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "alembic upgrade head failed after ${max_attempts} attempts" >&2
        exit 1
    fi
    echo "alembic upgrade head failed (attempt ${attempt}/${max_attempts}), retrying in 3s..." >&2
    attempt=$((attempt + 1))
    sleep 3
done

cd /app
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
