#!/usr/bin/env bash
# Schedule the article agent and the WhatsApp intake on this Mac: every day at 09:15 (local time).
# The article model is the local Antigravity CLI (agy, gemini-4-neon, medium effort), signed in once with `agy`.
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.qayem.articles.daily.plist"
mkdir -p "$QAYEM_ROOT/logs" "$(dirname "$PLIST")"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.qayem.articles.daily</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd "$QAYEM_ROOT" &amp;&amp; .venv/bin/qayem articles; .venv/bin/qayem extract-inbox</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
  <key>StandardOutPath</key><string>$QAYEM_ROOT/logs/articles.log</string>
  <key>StandardErrorPath</key><string>$QAYEM_ROOT/logs/articles.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Scheduled: $PLIST (logs/articles.log)"
