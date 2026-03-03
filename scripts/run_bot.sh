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

if [ ! -f "$ROOT/manage.py" ]; then
  echo "❌ manage.py not found in $ROOT" >&2
  exit 1
fi

PYTHON="$ROOT/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "❌ venv not found: $PYTHON. Run: python -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# Проверка PyMySQL до запуска бота
"$PYTHON" -c "import pymysql; pymysql.install_as_MySQLdb(); print('PyMySQL OK')" || {
  echo "❌ PyMySQL not installed in venv. Run: $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
}

exec "$PYTHON" "$ROOT/manage.py" run_bot "$@"
