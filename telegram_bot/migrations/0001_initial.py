from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramClient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_id", models.BigIntegerField(db_index=True, unique=True, verbose_name="Telegram ID")),
                ("telegram_username", models.CharField(blank=True, max_length=100, verbose_name="Telegram username")),
                ("first_name", models.CharField(blank=True, max_length=100, verbose_name="Имя")),
                ("last_name", models.CharField(blank=True, max_length=100, verbose_name="Фамилия")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(default=timezone.now)),
                (
                    "last_specialist",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="last_clients",
                        to="bookings.specialist",
                        verbose_name="Последний специалист",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TelegramClientSpecialist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_booked_at", models.DateTimeField(default=timezone.now)),
                ("last_booked_at", models.DateTimeField(default=timezone.now)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="telegram_bot.telegramclient")),
                ("specialist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bookings.specialist")),
            ],
            options={
                "unique_together": {("client", "specialist")},
            },
        ),
        migrations.AddField(
            model_name="telegramclient",
            name="specialists",
            field=models.ManyToManyField(blank=True, related_name="telegram_clients", through="telegram_bot.TelegramClientSpecialist", to="bookings.specialist"),
        ),
    ]


