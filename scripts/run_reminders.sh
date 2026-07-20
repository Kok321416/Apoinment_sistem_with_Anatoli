#!/usr/bin/env bash
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

PYTHON="${ROOT}/venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python"

exec "$PYTHON" -m app.commands.send_reminders "$@"
