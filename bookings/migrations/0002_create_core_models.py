# Migration that creates the real bookings models (Specialist, Calendar, Service, etc.)
# 0001_initial only created Consultant; this runs after it so 0003 can add fields to Calendar.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_type", models.CharField(choices=[("specialist", "Специалист"), ("client", "Клиент")], max_length=20, verbose_name="Тип пользователя")),
                ("telegram_username", models.CharField(blank=True, max_length=100, verbose_name="Telegram username")),
                ("telegram_id", models.BigIntegerField(blank=True, null=True, unique=True, verbose_name="Telegram ID")),
                ("phone", models.CharField(blank=True, max_length=20, verbose_name="Телефон")),
                ("bio", models.TextField(blank=True, verbose_name="О себе")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Specialist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("specialization", models.CharField(choices=[("psychology", "Психология"), ("law", "Юриспруденция"), ("medicine", "Медицина"), ("finance", "Финансы"), ("education", "Образование"), ("beauty", "Сфера красоты"), ("coaching", "Коучинг"), ("hr", "HR и подбор персонала"), ("business", "Бизнес и финансы"), ("fitness", "Фитнес и спорт")], max_length=50, verbose_name="Специализация")),
                ("invite_link", models.CharField(max_length=100, unique=True, verbose_name="Пригласительная ссылка")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="specialist", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Calendar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="Название календаря")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("color", models.CharField(default="#8b5cf6", max_length=7, verbose_name="Цвет календаря")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("specialist", models.ForeignKey(on_delete=models.CASCADE, related_name="calendars", to="bookings.specialist")),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("specialist", "name")},
            },
        ),
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Название услуги")),
                ("description", models.TextField(blank=True, verbose_name="Описание услуги")),
                ("duration", models.IntegerField(default=60, verbose_name="Длительность (минуты)")),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Цена")),
                ("invite_link", models.CharField(max_length=100, unique=True, verbose_name="Пригласительная ссылка")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("work_hours_start", models.TimeField(default="09:00", verbose_name="Начало рабочего дня")),
                ("work_hours_end", models.TimeField(default="18:00", verbose_name="Конец рабочего дня")),
                ("buffer_time", models.IntegerField(default=0, verbose_name="Буферное время между записями (минуты)")),
                ("calendar", models.ForeignKey(on_delete=models.CASCADE, related_name="services", to="bookings.calendar", verbose_name="Календарь")),
                ("specialist", models.ForeignKey(on_delete=models.CASCADE, related_name="services", to="bookings.specialist")),
            ],
        ),
        migrations.CreateModel(
            name="TimeSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="Дата")),
                ("start_time", models.TimeField(verbose_name="Время начала")),
                ("end_time", models.TimeField(verbose_name="Время окончания")),
                ("is_available", models.BooleanField(default=True, verbose_name="Доступен")),
                ("is_booked", models.BooleanField(default=False, verbose_name="Забронирован")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("calendar", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="time_slots", to="bookings.calendar")),
                ("service", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="time_slots", to="bookings.service")),
                ("specialist", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="old_time_slots", to="bookings.specialist")),
            ],
            options={
                "ordering": ["date", "start_time"],
                "unique_together": {("calendar", "date", "start_time")},
            },
        ),
        migrations.CreateModel(
            name="Appointment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("appointment_date", models.DateTimeField(verbose_name="Дата и время записи")),
                ("duration", models.IntegerField(default=60, verbose_name="Длительность (минуты)")),
                ("status", models.CharField(choices=[("pending", "Ожидает подтверждения"), ("confirmed", "Подтверждена"), ("cancelled", "Отменена"), ("completed", "Завершена")], default="pending", max_length=20, verbose_name="Статус")),
                ("notes", models.TextField(blank=True, verbose_name="Заметки")),
                ("client_name", models.CharField(max_length=100, verbose_name="Имя клиента")),
                ("client_email", models.EmailField(max_length=254, verbose_name="Email клиента")),
                ("client_phone", models.CharField(blank=True, max_length=20, verbose_name="Телефон клиента")),
                ("client_telegram", models.CharField(blank=True, max_length=100, verbose_name="Telegram клиента")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("calendar", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="appointments", to="bookings.calendar", verbose_name="Календарь")),
                ("client", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="appointments", to=settings.AUTH_USER_MODEL)),
                ("service", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="appointments", to="bookings.service", verbose_name="Услуга")),
                ("specialist", models.ForeignKey(on_delete=models.CASCADE, related_name="appointments", to="bookings.specialist")),
                ("time_slot", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="appointments", to="bookings.timeslot")),
            ],
            options={
                "ordering": ["-appointment_date"],
            },
        ),
    ]
