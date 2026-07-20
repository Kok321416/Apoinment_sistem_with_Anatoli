#!/usr/bin/env bash
# Stop all Telegram bot processes for this project.
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

PIDFILE="$ROOT/bot.pid"
LOCKFILE="$ROOT/bot.lock"
VENV_PYTHON="$ROOT/venv/bin/python"
BOT_PATTERN="${VENV_PYTHON} -m bot.run"

echo "Stopping Telegram bot in $ROOT"

_kill_pids() {
  local sig="$1"
  local pids=""
  if [ -x "$VENV_PYTHON" ]; then
    pids="$(pgrep -f "$BOT_PATTERN" 2>/dev/null || true)"
  fi
  if [ -z "$pids" ]; then
    pids="$(pgrep -f "${ROOT}.*bot\.run" 2>/dev/null || true)"
  fi
  if [ -z "$pids" ]; then
    pids="$(pgrep -f '[m]bot.run' 2>/dev/null || true)"
  fi
  if [ -n "$pids" ]; then
    echo "Sending SIG${sig} to: $pids"
    kill "-$sig" $pids 2>/dev/null || true
  fi
}

if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ]; then
    kill -TERM "$OLD_PID" 2>/dev/null || true
    sleep 2
    kill -KILL "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

_kill_pids TERM
sleep 2
_kill_pids KILL
rm -f "$LOCKFILE"

REMAINING="$(pgrep -af "${ROOT}.*bot\.run" 2>/dev/null || true)"
if [ -n "$REMAINING" ]; then
  echo "WARNING: bot process still running:"
  echo "$REMAINING"
  exit 1
fi

echo "Bot stopped"
