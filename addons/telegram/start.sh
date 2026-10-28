#!/usr/bin/env bash
# Start the ReelReady Telegram bridge in the background.
# Usage: ./start.sh "/path/to/AI Video Editor"      (or set REELREADY_MAIN)
#        ./start.sh "/path/to/AI Video Editor" --foreground
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="${1:-${REELREADY_MAIN:-}}"
if [ -z "$MAIN" ] || [ ! -d "$MAIN" ]; then
  echo "Give me your main folder: ./start.sh \"/path/to/AI Video Editor\"" >&2
  exit 1
fi
MAIN="$(cd "$MAIN" && pwd)"
WORK="$MAIN/.reelready/work"
PID_FILE="$WORK/telegram.pid"
LOG_FILE="$WORK/telegram.log"
mkdir -p "$WORK"

if [ ! -f "$MAIN/.reelready/.env" ]; then
  echo "Missing $MAIN/.reelready/.env (needs TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS)." >&2
  exit 1
fi
if ! python3 -c "import requests" 2>/dev/null; then
  echo "Python 'requests' is missing. Run: python3 -m pip install --user requests" >&2
  exit 1
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Already running (pid $(cat "$PID_FILE"))."
  exit 0
fi

if [ "${2:-}" = "--foreground" ]; then
  exec python3 "$HERE/bridge.py" --main-folder "$MAIN"
fi

nohup python3 "$HERE/bridge.py" --main-folder "$MAIN" >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Started (pid $(cat "$PID_FILE")). Log: $LOG_FILE"
else
  echo "It stopped right away. Last log lines:" >&2
  tail -n 10 "$LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi
