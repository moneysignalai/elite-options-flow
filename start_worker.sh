#!/usr/bin/env bash
set -euo pipefail

echo "Running alembic upgrade head..."
if ! PYTHONPATH=. alembic upgrade head; then
  echo "alembic upgrade failed" >&2
  exit 1
fi

PYTHONPATH=. python -m src.worker
