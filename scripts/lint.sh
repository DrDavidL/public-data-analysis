#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Running ruff check..."
uv run --directory backend ruff check backend/

echo "Running ruff format check..."
uv run --directory backend ruff format --check backend/

echo "All lint checks passed."
