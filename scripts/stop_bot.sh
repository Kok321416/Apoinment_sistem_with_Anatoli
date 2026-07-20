#!/usr/bin/env bash
# Stop all Telegram bot processes for this project.
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

PIDFILE="$ROOT/bot.pid"
LOCKFILE="$ROOT/bot.lock"

echo "Stopping Telegram bot in $ROOT"

if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ]; then
    kill -TERM "$OLD_PID" 2>/dev/null || true
    sleep 2
    kill -KILL "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

# [m] trick avoids matching pkill/sh argv
pkill -TERM -f '[m]bot.run' 2>/dev/null || true
pkill -TERM -f '[m]bot/run.py' 2>/dev/null || true
sleep 2
pkill -KILL -f '[m]bot.run' 2>/dev/null || true
pkill -KILL -f '[m]bot/run.py' 2>/dev/null || true

rm -f "$LOCKFILE"

if pgrep -af '[m]bot.run' >/dev/null 2>&1; then
  echo "WARNING: bot process still running:"
  pgrep -af '[m]bot.run' || true
  exit 1
fi

echo "Bot stopped"
