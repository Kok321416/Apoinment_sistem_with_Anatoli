#!/usr/bin/env python
"""
Одноразовый фикс: удаляет из django_migrations записи со старыми именами миграций
bookings (0002_calendar_day_settings, 0003_google_calendar_fields, 0004_telegram_link_token),
чтобы устранить конфликт с новой нумерацией (0003, 0004, 0005).
Запуск из корня проекта: python manage.py shell < scripts/fix_bookings_migration_names.py
или: python scripts/fix_bookings_migration_names.py (если DJANGO_SETTINGS_MODULE и путь настроены)
"""
import os
import sys
import django

# Загрузка Django (корень проекта = родитель каталога scripts)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appoiment_system.settings')
django.setup()

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
print(f"Deleted {deleted} old bookings migration row(s).")
