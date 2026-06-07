#!/usr/bin/env bash
# Apply migrations, then serve. Railway injects $PORT.
#
# NOTE: migrations run on every boot, which is safe for a SINGLE instance. Before scaling to
# more than one replica, move `alembic upgrade head` to a one-off release/pre-deploy step —
# otherwise simultaneous boots race on the migration.
set -euo pipefail

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
