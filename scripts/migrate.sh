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
  set +e
  MIGRATE_SYS_OUT=$(python manage.py migrate --noinput 2>&1)
  MIGRATE_SYS_R=$?
  set -e
  if [ $MIGRATE_SYS_R -ne 0 ]; then
    if echo "$MIGRATE_SYS_OUT" | grep -q "Duplicate column\|(1060,\|already exists"; then
      echo "⚠️ consultant_menu: колонки уже есть в БД. Помечаем миграции 0016/0017 как применённые (--fake), затем migrate."
      python manage.py migrate consultant_menu 0016_calendar_reminder_hours --fake
      python manage.py migrate consultant_menu 0017_booking_google_event_id --fake
      python manage.py migrate --noinput
    else
      echo "$MIGRATE_SYS_OUT"
      exit $MIGRATE_SYS_R
    fi
  else
    echo "$MIGRATE_SYS_OUT"
  fi
  python manage.py collectstatic --noinput
  cd "$ROOT_DIR"
  echo "✅ appoinment_sistem done"
else
  echo "⚠️ appoinment_sistem not found, skip"
fi

# 2) Бот и записи — appoiment_system (bookings, telegram_bot), корневой manage.py
if [ -f "manage.py" ]; then
  echo "🔄 Migrating appoiment_system (bookings, telegram_bot)..."
  # Удаляем старые файлы миграций от прошлой нумерации (иначе "multiple leaf nodes")
  rm -f bookings/migrations/0002_calendar_day_settings.py \
       bookings/migrations/0003_google_calendar_fields.py \
       bookings/migrations/0004_telegram_link_token.py
  set +e
  MIGRATE_OUT=$(python manage.py migrate --noinput 2>&1)
  MIGRATE_R=$?
  set -e
  if [ $MIGRATE_R -ne 0 ]; then
    if echo "$MIGRATE_OUT" | grep -q "Conflicting migrations\|multiple leaf"; then
      echo "⚠️ Conflicting migration names (old 0002/0003/0004 vs new 0003/0004/0005). Fixing: remove old rows, then --fake new."
      python manage.py shell < scripts/fix_bookings_migration_names_inline.py
      python manage.py migrate bookings 0005_telegram_link_token --fake
    elif echo "$MIGRATE_OUT" | grep -q "Duplicate column\|(1060,"; then
      echo "⚠️ Schema already applied by old migrations (Duplicate column). Marking bookings up to 0006 as applied (--fake), then re-running migrate."
      python manage.py migrate bookings 0006_sync_model_state --fake 2>/dev/null || python manage.py migrate bookings 0005_telegram_link_token --fake
      python manage.py migrate --noinput
    else
      echo "$MIGRATE_OUT"
      exit $MIGRATE_R
    fi
  else
    echo "$MIGRATE_OUT"
    # Если Django сообщает о неотражённых изменениях в моделях — создаём миграции и применяем снова
    if echo "$MIGRATE_OUT" | grep -q "have changes that are not yet reflected"; then
      echo "⚠️ Bookings: создаём миграции для неотражённых изменений..."
      python manage.py makemigrations bookings --noinput 2>/dev/null || true
      python manage.py migrate --noinput
    fi
  fi
  echo "✅ appoiment_system done"
else
  echo "⚠️ manage.py not found, skip"
fi

echo "✅ All migrations applied"
