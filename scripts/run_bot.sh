#!/usr/bin/env bash
# Запуск Telegram-бота (один экземпляр через flock).
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
if [ -n "${APP_DIR:-}" ]; then
  ROOT="$APP_DIR"
else
  export APP_DIR="$ROOT"
fi
cd "$ROOT"

PYTHON="${ROOT}/venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python"

LOCKFILE="$ROOT/bot.lock"
PIDFILE="$ROOT/bot.pid"

exec 200>"$LOCKFILE"
if ! flock -n 200; then
  echo "Bot already running (bot.lock). Skip second start."
  exit 0
fi

echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

exec "$PYTHON" -m bot.run "$@"
