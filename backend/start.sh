#!/bin/sh
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Launching ARQ background worker daemon..."
python -m arq app.workers.main.WorkerSettings &
WORKER_PID=$!

echo "==> Starting FastAPI Uvicorn server on port ${PORT:-8000}..."
trap "kill -TERM $WORKER_PID 2>/dev/null || true" EXIT INT TERM

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
