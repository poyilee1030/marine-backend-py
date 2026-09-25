#!/usr/bin/env bash
# Start marine-backend-py on :8100 with auto-reload.
set -euo pipefail
cd "$(dirname "$0")/.."
# ~/.bashrc sources ROS Humble, whose PYTHONPATH points at Python 3.10 site-packages
# and would be searched before this project's 3.12 venv.
unset PYTHONPATH
exec uv run uvicorn marine_backend.main:app --port "${PORT:-8100}" --reload
