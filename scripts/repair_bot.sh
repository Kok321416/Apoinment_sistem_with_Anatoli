#!/usr/bin/env bash
# One-shot repair: stop orphans, recreate venv, start single bot instance.
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-/opt/python/python-3.10.1/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3.10 || command -v python3)"
fi

echo "=== repair_bot in $ROOT ==="
echo "Using PYTHON_BIN=$PYTHON_BIN"

bash "$ROOT/scripts/stop_bot.sh" || true
# Force-kill stubborn PIDs if stop script reported leftovers
for pid in $(pgrep -f "${ROOT}.*bot\.run" 2>/dev/null || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1

rm -rf "$ROOT/venv"
"$PYTHON_BIN" -m venv "$ROOT/venv"
"$ROOT/venv/bin/python" -m ensurepip --upgrade 2>/dev/null || true
"$ROOT/venv/bin/python" -m pip install --upgrade pip
"$ROOT/venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$ROOT/venv/bin/python" -c "import requests; print('requests OK')"

: > "$ROOT/bot.log"
nohup env APP_DIR="$ROOT" bash "$ROOT/scripts/run_bot.sh" >> "$ROOT/bot.log" 2>&1 &
sleep 3
pgrep -af "${ROOT}.*bot\.run" || { echo "Bot failed to start:"; tail -20 "$ROOT/bot.log"; exit 1; }
echo "=== repair_bot done ==="
