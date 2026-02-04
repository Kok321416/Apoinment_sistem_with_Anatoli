# Generated manually - настройки календаря на каждый день

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0010_integration_google_refresh_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendar",
            name="break_between_services_minutes",
            field=models.PositiveIntegerField(default=0, verbose_name="Перерыв между услугами (минуты)"),
        ),
        migrations.AddField(
            model_name="calendar",
            name="book_ahead_hours",
            field=models.PositiveIntegerField(default=24, verbose_name="Запись не позднее чем за (часов)"),
        ),
        migrations.AddField(
            model_name="calendar",
            name="max_services_per_day",
            field=models.PositiveIntegerField(default=0, verbose_name="Лимит записей в день (0 — без лимита)"),
        ),
    ]
