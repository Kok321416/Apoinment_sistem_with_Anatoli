# Код для запуска через: python manage.py shell < scripts/fix_bookings_migration_names_inline.py
# Удаляет старые записи миграций bookings из django_migrations (та же БД, что и migrate).
from django.db import connection

OLD_NAMES = (
    '0002_calendar_day_settings',
    '0003_google_calendar_fields',
    '0004_telegram_link_token',
)
with connection.cursor() as c:
    placeholders = ", ".join(["%s"] * len(OLD_NAMES))
    c.execute(
        "DELETE FROM django_migrations WHERE app = 'bookings' AND name IN (" + placeholders + ")",
        OLD_NAMES,
    )
    deleted = c.rowcount
print("Deleted", deleted, "old bookings migration row(s).")
