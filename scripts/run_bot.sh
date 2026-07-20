#!/usr/bin/env bash
# Запуск Telegram-бота всегда через venv проекта (чтобы был доступен PyMySQL и остальные зависимости).
# Использование: из корня репозитория ./scripts/run_bot.sh
# Или: APP_DIR=/path/to/app ./scripts/run_bot.sh
# Если APP_DIR не задан — берём корень репозитория по пути скрипта (родитель каталога scripts/).

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

exec "$PYTHON" -m bot.run "$@"
