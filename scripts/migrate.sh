#!/usr/bin/env bash
# Применяет миграции для обоих Django-проектов (appoinment_sistem + appoiment_system).
# Запуск: из корня репозитория (APP_DIR): ./scripts/migrate.sh
# При деплое вызывается из .github/workflows/deploy.yml

set -e

# Корень проекта (каталог, где лежат appoinment_sistem/, manage.py, .env)
ROOT_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

echo "📁 APP_DIR=$ROOT_DIR"

# Активируем venv, если есть
if [ -d "venv" ]; then
  . venv/bin/activate
  pip install -q --upgrade certifi
  echo "✅ venv activated"
else
  echo "⚠️ venv not found, using system python"
fi

# 1) Основной сайт — appoinment_sistem (consultant_menu)
if [ -d "appoinment_sistem" ] && [ -f "appoinment_sistem/manage.py" ]; then
  echo "🔄 Migrating appoinment_sistem..."
  cd appoinment_sistem
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  cd "$ROOT_DIR"
  echo "✅ appoinment_sistem done"
else
  echo "⚠️ appoinment_sistem not found, skip"
fi

# 2) Бот и записи — appoiment_system (bookings, telegram_bot), корневой manage.py
if [ -f "manage.py" ]; then
  echo "🔄 Migrating appoiment_system (bookings, telegram_bot)..."
  python manage.py migrate --noinput
  echo "✅ appoiment_system done"
else
  echo "⚠️ manage.py not found, skip"
fi

echo "✅ All migrations applied"
