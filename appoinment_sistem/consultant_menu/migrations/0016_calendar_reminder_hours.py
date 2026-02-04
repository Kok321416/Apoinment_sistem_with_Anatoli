# Calendar: за сколько часов до консультации отправлять напоминания в Telegram

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0015_booking_specialist_reminders"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendar",
            name="reminder_hours_first",
            field=models.PositiveIntegerField(
                default=24,
                help_text="Напоминание в Telegram за N часов до консультации (например 24 = за сутки)",
                verbose_name="Первое напоминание за (часов)",
            ),
        ),
        migrations.AddField(
            model_name="calendar",
            name="reminder_hours_second",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Второе напоминание за N часов до консультации (например 1 = за час)",
                verbose_name="Второе напоминание за (часов)",
            ),
        ),
    ]
