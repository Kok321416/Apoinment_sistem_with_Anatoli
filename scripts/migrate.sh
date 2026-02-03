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
  set +e
  MIGRATE_OUT=$(python manage.py migrate --noinput 2>&1)
  MIGRATE_R=$?
  set -e
  if [ $MIGRATE_R -ne 0 ]; then
    if echo "$MIGRATE_OUT" | grep -q "Conflicting migrations\|multiple leaf"; then
      echo "⚠️ Conflicting migration names (old 0002/0003/0004 vs new 0003/0004/0005). Fixing: remove old rows, then --fake new."
      python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
  c.execute(\"DELETE FROM django_migrations WHERE app='bookings' AND name IN ('0002_calendar_day_settings', '0003_google_calendar_fields', '0004_telegram_link_token')\")
"
      python manage.py migrate bookings 0005_telegram_link_token --fake
    else
      echo "$MIGRATE_OUT"
      exit $MIGRATE_R
    fi
  else
    echo "$MIGRATE_OUT"
  fi
  echo "✅ appoiment_system done"
else
  echo "⚠️ manage.py not found, skip"
fi

echo "✅ All migrations applied"
