#!/usr/bin/env bash
# Деплой на сервере: venv, зависимости, миграции, gunicorn, Telegram-бот.
# Бот всегда запускается через scripts/run_bot.sh (venv), чтобы был доступен PyMySQL.
# Запуск: APP_DIR=/path/to/app ./entrypoint.sh
# Или из каталога приложения: ./entrypoint.sh

set -e
APP_DIR="${APP_DIR:-$(pwd)}"
cd "$APP_DIR"
export APP_DIR

export PATH="${PATH:-$HOME/.local/bin:$HOME/bin:/usr/local/bin:/usr/bin:/bin}"

echo "📁 APP_DIR=$APP_DIR"

# Python
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "/opt/python/python-3.10.1/bin/python" ]; then
    PYTHON_BIN="/opt/python/python-3.10.1/bin/python"
  elif command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN="python3.10"
  else
    PYTHON_BIN="python3"
  fi
fi
echo "🐍 PYTHON_BIN=$PYTHON_BIN"

# venv: создать или переиспользовать
if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi
. venv/bin/activate
python -m ensurepip --upgrade 2>/dev/null || true
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q
python -m pip install -q python-dotenv
python -c "import pymysql; print('PyMySQL', pymysql.__version__, 'OK')" || { echo "❌ PyMySQL not in venv. pip install -r requirements.txt"; exit 1; }
python -c "from dotenv import load_dotenv; print('python-dotenv OK')" || { echo "❌ python-dotenv not in venv (required by appoiment_system.settings)"; exit 1; }

# Миграции (оба проекта)
chmod +x scripts/migrate.sh scripts/run_bot.sh 2>/dev/null || true
./scripts/migrate.sh

# Gunicorn
PIDFILE="$APP_DIR/gunicorn.pid"
LOGFILE="$APP_DIR/gunicorn.log"
DJANGO_DIR="appoinment_sistem"
if [ -f "$PIDFILE" ]; then
  kill -TERM "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
  sleep 2
fi
nohup "$APP_DIR/venv/bin/gunicorn" --chdir "$DJANGO_DIR" appoinment_sistem.wsgi:application \
  --bind 127.0.0.1:8000 --workers 2 --pid "$PIDFILE" \
  > "$LOGFILE" 2>&1 &
echo "✅ Gunicorn started"

# Telegram-бот — всегда через scripts/run_bot.sh (там используется venv/bin/python)
BOT_PIDFILE="$APP_DIR/bot.pid"
BOT_LOG="$APP_DIR/bot.log"
if [ -f "$BOT_PIDFILE" ]; then
  OLD_PID=$(cat "$BOT_PIDFILE")
  kill -TERM "$OLD_PID" 2>/dev/null || true
  rm -f "$BOT_PIDFILE"
  sleep 2
fi
: > "$BOT_LOG"
nohup "$APP_DIR/scripts/run_bot.sh" >> "$BOT_LOG" 2>&1 &
echo $! > "$BOT_PIDFILE"
sleep 2
if kill -0 "$(cat "$BOT_PIDFILE")" 2>/dev/null; then
  echo "✅ Telegram bot started (PID $(cat "$BOT_PIDFILE"))"
else
  echo "⚠️ Bot may have exited. Check $BOT_LOG"
fi

echo "✅ Deploy done. Gunicorn: $LOGFILE, Bot: $BOT_LOG"
