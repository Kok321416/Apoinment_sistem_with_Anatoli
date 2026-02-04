# Generated manually: одноразовый токен для подключения Telegram специалиста через приложение

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0013_booking_reminder_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="integration",
            name="telegram_link_token",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="integration",
            name="telegram_link_token_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
