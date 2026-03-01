#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Start backend
echo "Starting backend on :8000..."
(cd backend && uv run fastapi dev app/main.py --port 8000) &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on :5173..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
