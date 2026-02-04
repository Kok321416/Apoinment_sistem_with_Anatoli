# Generated manually: напоминания специалисту в Telegram (24ч и 1ч)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0014_integration_telegram_link_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="specialist_reminder_24h_sent",
            field=models.BooleanField(default=False, verbose_name="Напоминание специалисту за 24ч отправлено"),
        ),
        migrations.AddField(
            model_name="booking",
            name="specialist_reminder_1h_sent",
            field=models.BooleanField(default=False, verbose_name="Напоминание специалисту за 1ч отправлено"),
        ),
    ]
