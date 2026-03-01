#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Running pip-audit..."
uv export --directory backend --format requirements-txt --no-hashes | \
  uv run --directory backend pip-audit -r /dev/stdin --no-deps

echo "Audit passed."
