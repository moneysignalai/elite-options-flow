#!/usr/bin/env bash
set -euo pipefail
python -m uvicorn src.main_web:app --host 0.0.0.0 --port 8000
