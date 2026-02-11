#!/usr/bin/env bash
# Запуск отправки напоминаний о консультациях в Telegram.
# Использует настройки календаря (reminder_hours_first, reminder_hours_second) для каждой записи.
# Запуск: из корня репозитория ./scripts/run_reminders.sh
# Для автоматизации добавьте в cron (каждые 15–30 мин). Подставьте свой путь к проекту:
#   */20 * * * * /var/www/Online_appointment_for_consultations/scripts/run_reminders.sh >> /var/www/Online_appointment_for_consultations/logs/reminders.log 2>&1
# Подробнее: scripts/cron_reminders.example и LOGS_AND_COMMANDS.md

set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

if [ ! -d "appoinment_sistem" ] || [ ! -f "appoinment_sistem/manage.py" ]; then
  echo "❌ appoinment_sistem/manage.py not found in $ROOT" >&2
  exit 1
fi

# Сначала ищем venv в корне проекта, затем на уровень выше (reg.ru: venv в data/)
PYTHON="${ROOT}/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(cd "$ROOT/.." 2>/dev/null && pwd)/venv/bin/python"
fi
if [ ! -x "$PYTHON" ]; then
  [ -n "${PYTHON_PATH:-}" ] && PYTHON="$PYTHON_PATH"
fi
if [ ! -x "$PYTHON" ]; then
  echo "❌ venv not found. Проверьте ROOT/venv или ROOT/../venv, либо задайте PYTHON_PATH" >&2
  exit 1
fi

cd "$ROOT/appoinment_sistem"
exec "$PYTHON" manage.py send_booking_reminders
