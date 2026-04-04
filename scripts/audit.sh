#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Running pip-audit..."
# CVE-2025-69872 (diskcache pickle deserialization): mitigated by using
# a custom JSON-only Disk subclass in http_client.py — no pickle used.
uv export --directory backend --format requirements-txt --no-hashes | \
  uv run --directory backend pip-audit -r /dev/stdin --no-deps \
    --ignore-vuln CVE-2025-69872

echo "Audit passed."
