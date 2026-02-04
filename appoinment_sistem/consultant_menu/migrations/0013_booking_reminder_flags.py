# Generated manually: флаги напоминаний клиенту в Telegram

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultant_menu', '0012_booking_telegram_link'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='reminder_24h_sent',
            field=models.BooleanField(default=False, verbose_name='Напоминание за 24ч отправлено'),
        ),
        migrations.AddField(
            model_name='booking',
            name='reminder_1h_sent',
            field=models.BooleanField(default=False, verbose_name='Напоминание за 1ч отправлено'),
        ),
    ]
