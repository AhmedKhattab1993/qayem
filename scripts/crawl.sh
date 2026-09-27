#!/usr/bin/env bash
# Nightly crawl of every source, then description enrichment (run by cron; safe to run by hand).
# One crawl at a time: a second invocation exits while the first holds the lock.
# Logs: logs/crawl-YYYY-MM-DD.log (kept 30 days). Health: logs/health.json.
set -uo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QAYEM_ROOT"
mkdir -p logs
export COLUMNS=140 TERM=dumb PYTHONUNBUFFERED=1
# cron's PATH lacks the user's tools; description enrichment needs the codex CLI
export PATH="$HOME/.local/bin:$PATH"

exec 9>logs/crawl.lock
if ! flock -n 9; then
  echo "$(date -Is) crawl already running; skipped" >> logs/crawl-skipped.log
  exit 0
fi

log="logs/crawl-$(date +%F).log"
{
  echo "== crawl started $(date -Is)"
  .venv/bin/qayem crawl
  echo "== crawl exit $? at $(date -Is)"
  # fill missing fields of new listings from their text; failures never fail the crawl
  .venv/bin/qayem enrich-descriptions --batches 0 --workers 4 --max-minutes "${QAYEM_ENRICH_MINUTES:-120}"
  echo "== enrich exit $? at $(date -Is)"
  .venv/bin/qayem health --write logs/health.json
  echo "== health exit $?"
} >> "$log" 2>&1

find logs -name 'crawl-*.log' -mtime +30 -delete
