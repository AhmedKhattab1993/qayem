#!/usr/bin/env bash
# Nightly crawl of the sources in use (QAYEM_SOURCES, AqarExit by default) and the price benchmarks
# (QAYEM_BENCHMARK_SOURCES, Nawy's developer sales), then name resolution
# (run by cron; safe to run by hand).
# One crawl at a time: a second invocation exits while the first holds the lock.
# Logs: logs/crawl-YYYY-MM-DD.log (kept 30 days). Health: logs/health.json.
set -uo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QAYEM_ROOT"
mkdir -p logs
export COLUMNS=140 TERM=dumb PYTHONUNBUFFERED=1
# cron's PATH lacks the user's tools; name resolution needs the Pi CLI
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

exec 9>logs/crawl.lock
# macOS has no flock(1); perl takes the same non-blocking lock on fd 9 (6 = LOCK_EX|LOCK_NB)
lock_crawl() {
  if command -v flock >/dev/null; then flock -n 9
  else perl -e 'open(my $f, ">&=", 9) or exit 1; flock($f, 6) or exit 1'; fi
}
if ! lock_crawl; then
  echo "$(date -Is) crawl already running; skipped" >> logs/crawl-skipped.log
  exit 0
fi

log="logs/crawl-$(date +%F).log"
{
  echo "== crawl started $(date -Is)"
  .venv/bin/qayem crawl
  echo "== crawl exit $? at $(date -Is)"
  # parser fixes reach stored AqarExit units, whose unchanged pages are never refetched
  .venv/bin/qayem renormalize aqarexit
  echo "== renormalize exit $? at $(date -Is)"
  # canonical names for new compound/developer spellings (matches resale to the developers' prices)
  .venv/bin/qayem resolve-entities --workers 4 --max-minutes "${QAYEM_ENTITY_MINUTES:-30}"
  echo "== entities exit $? at $(date -Is)"
  .venv/bin/qayem health --write logs/health.json
  echo "== health exit $?"
  if [[ "${QAYEM_CLOUDFLARE_SYNC:-0}" == "1" ]]; then
    .venv/bin/python scripts/cloudflare-sync.py
    echo "== Cloudflare publication exit $? at $(date -Is)"
  fi
} >> "$log" 2>&1

find logs -name 'crawl-*.log' -mtime +30 -delete
