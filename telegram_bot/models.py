from django.db import models
from django.utils import timezone

from bookings.models import Specialist


class TelegramClient(models.Model):
    """
    Telegram-клиент (не обязательно Django User).
    Храним telegram_id и связь со специалистами, к которым клиент уже записывался.
    """

    telegram_id = models.BigIntegerField(unique=True, db_index=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(max_length=100, blank=True, verbose_name="Telegram username")
    first_name = models.CharField(max_length=100, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="Фамилия")

    last_specialist = models.ForeignKey(
        Specialist,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="last_clients",
        verbose_name="Последний специалист",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    specialists = models.ManyToManyField(
        Specialist,
        through="TelegramClientSpecialist",
        related_name="telegram_clients",
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.telegram_id} @{self.telegram_username}".strip()


class TelegramClientSpecialist(models.Model):
    """Связь TelegramClient ↔ Specialist с метаданными."""

    client = models.ForeignKey(TelegramClient, on_delete=models.CASCADE)
    specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE)
    first_booked_at = models.DateTimeField(default=timezone.now)
    last_booked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("client", "specialist")


