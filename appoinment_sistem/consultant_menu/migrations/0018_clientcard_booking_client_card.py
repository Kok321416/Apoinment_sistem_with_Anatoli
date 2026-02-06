# Карточки клиентов для специалиста + связь записей с карточкой

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0017_booking_google_event_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=255, null=True, verbose_name="Имя")),
                ("email", models.EmailField(blank=True, max_length=254, null=True, verbose_name="Email")),
                ("phone", models.CharField(blank=True, max_length=30, null=True, verbose_name="Телефон")),
                ("telegram", models.CharField(blank=True, max_length=255, null=True, verbose_name="Telegram (ник или ссылка)")),
                ("notes", models.TextField(blank=True, null=True, verbose_name="Примечания")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("consultant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="client_cards", to="consultant_menu.consultant")),
            ],
            options={
                "verbose_name": "Карточка клиента",
                "verbose_name_plural": "Карточки клиентов",
                "db_table": "consultant_client_cards",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddField(
            model_name="booking",
            name="client_card",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="consultant_menu.clientcard",
                verbose_name="Карточка клиента",
            ),
        ),
    ]
