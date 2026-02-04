# Booking: link_token, telegram_id для подтверждения в Telegram; time_slot nullable

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0011_calendar_day_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="link_token",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="Токен для привязки Telegram"),
        ),
        migrations.AddField(
            model_name="booking",
            name="telegram_id",
            field=models.BigIntegerField(blank=True, null=True, verbose_name="Telegram ID (после подтверждения в боте)"),
        ),
        migrations.AlterField(
            model_name="booking",
            name="time_slot",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="bookings", to="consultant_menu.timeslot"),
        ),
    ]
