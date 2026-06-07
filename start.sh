#!/usr/bin/env bash
# Apply migrations, then serve. Railway injects $PORT.
set -euo pipefail

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
