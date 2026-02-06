# Один пробный клиент в карточках (для первого специалиста в БД)

from django.db import migrations


def create_test_client_card(apps, schema_editor):
    Consultant = apps.get_model("consultant_menu", "Consultant")
    ClientCard = apps.get_model("consultant_menu", "ClientCard")
    if Consultant.objects.exists() and not ClientCard.objects.exists():
        consultant = Consultant.objects.first()
        ClientCard.objects.create(
            consultant=consultant,
            name="Пробный клиент",
            email="test.client@example.com",
            phone="+7 (999) 000-00-00",
            telegram="@test_client",
            notes="Карточка создана автоматически для проверки раздела «Карточки клиентов».",
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("consultant_menu", "0018_clientcard_booking_client_card"),
    ]

    operations = [
        migrations.RunPython(create_test_client_card, noop),
    ]
