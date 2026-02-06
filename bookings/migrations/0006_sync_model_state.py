# Migration to sync migration state with current models (no schema change).
# If the server still reports "models have changes", run on server:
#   python manage.py makemigrations bookings --noinput && python manage.py migrate --noinput
# then add the generated migration file to the repo.

from django.db import migrations


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0005_telegram_link_token"),
    ]

    operations = [
        migrations.RunPython(noop, noop),
    ]
