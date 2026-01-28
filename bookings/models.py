from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class UserProfile(models.Model):
    """Профиль пользователя с типом (специалист/клиент)"""
    USER_TYPE_CHOICES = [
        ('specialist', 'Специалист'),
        ('client', 'Клиент'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, verbose_name='Тип пользователя')
    telegram_username = models.CharField(max_length=100, verbose_name='Telegram username', blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name='Telegram ID')
    phone = models.CharField(max_length=20, verbose_name='Телефон', blank=True)
    bio = models.TextField(verbose_name='О себе', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} ({self.get_user_type_display()})"


class Specialist(models.Model):
    """Модель специалиста"""
    SPECIALIZATION_CHOICES = [
        ('psychology', 'Психология'),
        ('law', 'Юриспруденция'),
        ('medicine', 'Медицина'),
        ('finance', 'Финансы'),
        ('education', 'Образование'),
        ('beauty', 'Сфера красоты'),
        ('coaching', 'Коучинг'),
        ('hr', 'HR и подбор персонала'),
        ('business', 'Бизнес и финансы'),
        ('fitness', 'Фитнес и спорт'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='specialist')
    specialization = models.CharField(max_length=50, choices=SPECIALIZATION_CHOICES, verbose_name='Специализация')
    invite_link = models.CharField(max_length=100, unique=True, verbose_name='Пригласительная ссылка')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        if not self.invite_link:
            # Генерируем уникальную ссылку
            self.invite_link = f"specialist-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_specialization_display()}"


class Calendar(models.Model):
    """Календарь специалиста (для разных типов работы или временных рамок)"""
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name='calendars')
    name = models.CharField(max_length=100, verbose_name='Название календаря')
    description = models.TextField(blank=True, verbose_name='Описание')
    color = models.CharField(max_length=7, default='#8b5cf6', verbose_name='Цвет календаря')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['specialist', 'name']
    
    def __str__(self):
        return f"{self.specialist.user.username} - {self.name}"


class Service(models.Model):
    """Услуга специалиста"""
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name='services')
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='services', verbose_name='Календарь')
    name = models.CharField(max_length=200, verbose_name='Название услуги')
    description = models.TextField(blank=True, verbose_name='Описание услуги')
    duration = models.IntegerField(verbose_name='Длительность (минуты)', default=60)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Цена')
    invite_link = models.CharField(max_length=100, unique=True, verbose_name='Пригласительная ссылка')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Настройки временных рамок
    work_hours_start = models.TimeField(default='09:00', verbose_name='Начало рабочего дня')
    work_hours_end = models.TimeField(default='18:00', verbose_name='Конец рабочего дня')
    buffer_time = models.IntegerField(default=0, verbose_name='Буферное время между записями (минуты)')
    
    def save(self, *args, **kwargs):
        if not self.invite_link:
            # Генерируем уникальную ссылку
            self.invite_link = f"service-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.specialist.user.username})"


class TimeSlot(models.Model):
    """Временной слот для записи"""
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='time_slots', null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='time_slots', null=True, blank=True)
    # Временная поддержка старой структуры
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name='old_time_slots', null=True, blank=True)
    date = models.DateField(verbose_name='Дата')
    start_time = models.TimeField(verbose_name='Время начала')
    end_time = models.TimeField(verbose_name='Время окончания')
    is_available = models.BooleanField(default=True, verbose_name='Доступен')
    is_booked = models.BooleanField(default=False, verbose_name='Забронирован')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date', 'start_time']
        unique_together = ['calendar', 'date', 'start_time']
    
    def __str__(self):
        return f"{self.calendar.name} - {self.date} {self.start_time}"


class Appointment(models.Model):
    """Запись на консультацию"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждена'),
        ('cancelled', 'Отменена'),
        ('completed', 'Завершена'),
    ]
    
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name='appointments')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='appointments', verbose_name='Услуга', null=True, blank=True)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='appointments', verbose_name='Календарь', null=True, blank=True)
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments', null=True, blank=True)
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='appointments', null=True, blank=True)
    appointment_date = models.DateTimeField(verbose_name='Дата и время записи')
    duration = models.IntegerField(default=60, verbose_name='Длительность (минуты)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    notes = models.TextField(verbose_name='Заметки', blank=True)
    client_name = models.CharField(max_length=100, verbose_name='Имя клиента')
    client_email = models.EmailField(verbose_name='Email клиента')
    client_phone = models.CharField(max_length=20, verbose_name='Телефон клиента', blank=True)
    client_telegram = models.CharField(max_length=100, verbose_name='Telegram клиента', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-appointment_date']
    
    def __str__(self):
        return f"{self.client_name} -> {self.service.name} ({self.appointment_date})"

