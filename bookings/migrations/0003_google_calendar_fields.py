# Generated manually for Google Calendar integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0002_calendar_day_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="specialist",
            name="google_refresh_token",
            field=models.CharField(blank=True, max_length=500, verbose_name="Google refresh token"),
        ),
        migrations.AddField(
            model_name="specialist",
            name="google_calendar_id",
            field=models.CharField(
                blank=True,
                default="primary",
                max_length=255,
                verbose_name="Google Calendar ID",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="google_event_id",
            field=models.CharField(blank=True, max_length=255, verbose_name="ID события в Google Calendar"),
        ),
    ]
