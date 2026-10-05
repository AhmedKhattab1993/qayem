#!/usr/bin/env bash
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QAYEM_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Python environment is missing. Run: uv venv .venv && uv pip install -e ".[dev,web]"' >&2
  exit 1
fi
if [[ ! -f web/dist/index.html ]]; then
  echo 'Website build is missing. Run: npm --prefix web ci && npm --prefix web run build' >&2
  exit 1
fi
# QAYEM_HOST=0.0.0.0 serves on every interface (the public IP); the default is this machine only
exec .venv/bin/python -m uvicorn qayem.web:app --host "${QAYEM_HOST:-127.0.0.1}" --port "${QAYEM_PORT:-8000}"
