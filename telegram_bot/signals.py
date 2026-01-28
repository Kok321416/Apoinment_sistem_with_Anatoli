from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from bookings.models import Appointment
from telegram_bot.models import TelegramClient, TelegramClientSpecialist


def _normalize_username(username: str) -> str:
    if not username:
        return ""
    username = username.strip()
    if username and not username.startswith("@"):
        username = "@" + username
    return username


@receiver(post_save, sender=Appointment)
def remember_client_specialist_from_appointment(sender, instance: Appointment, created: bool, **kwargs):
    """
    Если запись создана из мини‑приложения/бота и там известен telegram_id,
    запоминаем связь telegram клиента со специалистом.

    Сейчас telegram_id хранится в instance.notes как JSON не используется,
    поэтому актуальный путь — вызов из telegram_bot/views.py после валидации initData.
    Этот сигнал оставляем на будущее расширение (если начнем писать telegram_id в Appointment).
    """
    # Пока ничего не делаем, чтобы не плодить ложные связи.
    return


