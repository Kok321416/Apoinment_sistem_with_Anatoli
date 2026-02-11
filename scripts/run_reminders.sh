#!/usr/bin/env bash
# Запуск отправки напоминаний о консультациях в Telegram.
# Использует настройки календаря (reminder_hours_first, reminder_hours_second) для каждой записи.
# Запуск: из корня репозитория ./scripts/run_reminders.sh
# Для автоматизации добавьте в cron (каждые 15–30 мин), например:
#   */20 * * * * /путь/к/проекту/scripts/run_reminders.sh >> /путь/к/проекту/logs/reminders.log 2>&1

set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

if [ ! -d "appoinment_sistem" ] || [ ! -f "appoinment_sistem/manage.py" ]; then
  echo "❌ appoinment_sistem/manage.py not found in $ROOT" >&2
  exit 1
fi

PYTHON="${ROOT}/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "❌ venv not found: $PYTHON" >&2
  exit 1
fi

cd "$ROOT/appoinment_sistem"
exec "$PYTHON" manage.py send_booking_reminders
