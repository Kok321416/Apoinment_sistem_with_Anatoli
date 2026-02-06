# Добавление поля для хранения ID события в Google Calendar при синхронизации

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0016_calendar_reminder_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="google_event_id",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="ID события в Google Calendar"),
        ),
    ]
