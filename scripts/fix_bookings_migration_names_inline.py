# Код для запуска через: python manage.py shell < scripts/fix_bookings_migration_names_inline.py
# Удаляет конфликтующие записи миграций bookings (старые имена и дубликат 0004).
from django.db.migrations.recorder import MigrationRecorder

OLD_NAMES = (
    '0002_calendar_day_settings',
    '0003_google_calendar_fields',
    '0004_telegram_link_token',
)
Migration = MigrationRecorder.Migration
before = list(Migration.objects.filter(app='bookings').values_list('name', flat=True))
deleted, _ = Migration.objects.filter(app='bookings', name__in=OLD_NAMES).delete()
print("Deleted", deleted, "old bookings migration row(s). Before:", before)
