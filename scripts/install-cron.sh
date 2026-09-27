#!/usr/bin/env bash
# Install (or update) the nightly crawl in the current user's crontab.
# Default 02:30 local time; override with QAYEM_CRAWL_TIME="MM HH" (cron minute and hour).
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
when="${QAYEM_CRAWL_TIME:-30 2}"
line="$when * * * $QAYEM_ROOT/scripts/crawl.sh # qayem-nightly-crawl"
{ crontab -l 2>/dev/null | grep -v '# qayem-nightly-crawl' || true; echo "$line"; } | crontab -
echo "Installed: $line"
