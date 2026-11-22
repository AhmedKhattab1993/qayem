#!/usr/bin/env bash
# Schedule the monthly isolated-VM developer-pages & realestate.gov.eg terms check on this Mac:
# 1st of each month at 10:15 (local time), strictly inside the OrbStack `computer-use` VM
# behind content-engine's shared desktop lock (docs/STRATEGY.md 5.4).
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.qayem.vm-pages.monthly.plist"
mkdir -p "$QAYEM_ROOT/logs" "$(dirname "$PLIST")"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.qayem.vm-pages.monthly</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd "$QAYEM_ROOT" &amp;&amp; .venv/bin/python scripts/vm-developer-pages.py --wait 120</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Day</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>15</integer></dict>
  <key>StandardOutPath</key><string>$QAYEM_ROOT/logs/vm-pages.log</string>
  <key>StandardErrorPath</key><string>$QAYEM_ROOT/logs/vm-pages.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Scheduled: $PLIST (logs/vm-pages.log)"
