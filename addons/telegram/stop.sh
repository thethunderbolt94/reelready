#!/usr/bin/env bash
# Stop the ReelReady Telegram bridge.
# Usage: ./stop.sh "/path/to/AI Video Editor"      (or set REELREADY_MAIN)
set -euo pipefail

MAIN="${1:-${REELREADY_MAIN:-}}"
if [ -z "$MAIN" ] || [ ! -d "$MAIN" ]; then
  echo "Give me your main folder: ./stop.sh \"/path/to/AI Video Editor\"" >&2
  exit 1
fi
PID_FILE="$MAIN/.reelready/work/telegram.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
  echo "Stopped."
else
  rm -f "$PID_FILE"
  echo "Not running."
fi
