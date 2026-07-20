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
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: venv not found at $PYTHON"
  echo "Run on server:"
  echo "  cd $ROOT"
  echo "  /opt/python/python-3.10.1/bin/python -m venv venv"
  echo "  venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "$PYTHON" -c "import requests" 2>/dev/null; then
  echo "ERROR: Python packages missing in venv (requests). Run:"
  echo "  cd $ROOT && venv/bin/pip install -r requirements.txt"
  exit 1
fi

LOCKFILE="$ROOT/bot.lock"
PIDFILE="$ROOT/bot.pid"
STOP_SCRIPT="$SCRIPT_ABS/stop_bot.sh"

# Kill orphan pollers (e.g. started without flock or from old deploy)
if pgrep -f "${ROOT}/venv/bin/python -m bot.run" >/dev/null 2>&1; then
  echo "Stopping existing bot instance(s) in $ROOT ..."
  if [ -x "$STOP_SCRIPT" ]; then
    bash "$STOP_SCRIPT" || true
  else
    pgrep -f "${ROOT}/venv/bin/python -m bot.run" | xargs kill -9 2>/dev/null || true
  fi
  sleep 2
fi
rm -f "$LOCKFILE" "$PIDFILE"

exec 200>"$LOCKFILE"
if ! flock -n 200; then
  echo "Bot already running (bot.lock). Skip second start."
  exit 0
fi

echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

exec "$PYTHON" -m bot.run "$@"
