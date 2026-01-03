from django.db import models
from django.contrib.auth.models import User


class Clients(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True, null=False, db_index=True)
    number = models.IntegerField()
    telegram_nickname = models.CharField(max_length=255, blank=True, null=False)
    who_your_consultant_name = models.ForeignKey(on_delete=models.PROTECT, to="Consultant", null=False)

    class Meta:
        db_table = "clients"

    def __str__(self):
        return f"{self.name} {self.number}"


class Consultant(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, null=False)
    last_name = models.CharField(max_length=255, blank=True, null=False)
    middle_name = models.CharField(max_length=255, blank=True, null=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)
    telegram_nickname = models.CharField(max_length=255, blank=True, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category_of_specialist = models.ForeignKey(on_delete=models.PROTECT, to="Category")
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, related_name='consultant')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        db_table = "consultants"


class Category(models.Model):
    name_category = models.CharField(max_length=255, blank=True, null=False, db_index=True)


class Calendar(models.Model):
    """Календарь - консультант может иметь несколько календарей"""
    consultant = models.ForeignKey(Consultant, on_delete=models.CASCADE, related_name='calendars')
    name = models.CharField(max_length=255, verbose_name='Название календаря')
    color = models.CharField(max_length=7, default='#667eea', verbose_name='Цвет календаря')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'calendars'
        verbose_name = 'Календарь'
        verbose_name_plural = 'Календари'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.consultant})"


class TimeSlot(models.Model):
    """
    Временное окно - предустановленные слоты времени, которые консультант создает заранее.
    Например: "Понедельник 10:00-11:00", "Понедельник 14:00-15:00"
    """
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='time_slots')
    day_of_week = models.IntegerField(verbose_name='День недели', choices=[
        (0, 'Понедельник'),
        (1, 'Вторник'),
        (2, 'Среда'),
        (3, 'Четверг'),
        (4, 'Пятница'),
        (5, 'Суббота'),
        (6, 'Воскресенье'),
    ])
    start_time = models.TimeField(verbose_name='Время начала')
    end_time = models.TimeField(verbose_name='Время окончания')
    is_available = models.BooleanField(default=True, verbose_name='Доступен для записи')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'time_slots'
        verbose_name = 'Временное окно'
        verbose_name_plural = 'Временные окна'
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.start_time}-{self.end_time} ({self.calendar.name})"


class Service(models.Model):
    """
    Услуга - консультант создает услуги, которые можно выбрать для записи.
    Может быть несколько услуг.
    """
    consultant = models.ForeignKey(Consultant, on_delete=models.CASCADE, related_name='services')
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='services', null=True, blank=True)
    name = models.CharField(max_length=255, verbose_name='Название услуги')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    duration_minutes = models.IntegerField(verbose_name='Длительность (минуты)', default=60)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Цена')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'services'
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.consultant})"


class Booking(models.Model):
    """
    Запись - когда клиент выбирает услугу и время из доступных временных окон.
    """
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('confirmed', 'Подтверждена'),
        ('cancelled', 'Отменена'),
        ('completed', 'Завершена'),
    ]

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='bookings')
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='bookings')
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='bookings')

    # Информация о клиенте
    client_name = models.CharField(max_length=255, verbose_name='Имя клиента')
    client_phone = models.CharField(max_length=20, verbose_name='Телефон клиента')
    client_email = models.EmailField(blank=True, null=True, verbose_name='Email клиента')

    # Дата и время записи (конкретная дата)
    booking_date = models.DateField(verbose_name='Дата записи')
    booking_time = models.TimeField(verbose_name='Время записи')
    booking_end_time = models.TimeField(verbose_name='Время окончания записи', null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    notes = models.TextField(blank=True, null=True, verbose_name='Примечания')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bookings'
        verbose_name = 'Запись'
        verbose_name_plural = 'Записи'
        ordering = ['booking_date', 'booking_time']

    def __str__(self):
        return f"{self.client_name} - {self.service.name} ({self.booking_date} {self.booking_time})"
