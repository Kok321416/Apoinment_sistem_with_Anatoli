# Generated manually for calendar day settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_create_core_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='calendar',
            name='break_between_services_minutes',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Минут между окончанием одной записи и началом следующей.',
                verbose_name='Перерыв между услугами (минуты)',
            ),
        ),
        migrations.AddField(
            model_name='calendar',
            name='book_ahead_hours',
            field=models.PositiveIntegerField(
                default=24,
                help_text='Клиент может записаться только на слоты не раньше чем через N часов (например 24 = за сутки).',
                verbose_name='Запись не позднее чем за (часов)',
            ),
        ),
        migrations.AddField(
            model_name='calendar',
            name='max_services_per_day',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Максимум записей в один день по этому календарю. 0 = без лимита.',
                verbose_name='Лимит записей в день',
            ),
        ),
    ]
