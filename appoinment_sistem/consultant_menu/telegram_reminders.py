"""
Отправка уведомлений в Telegram: напоминания клиенту, уведомление специалисту о новой записи.
Используется management command send_booking_reminders и signal при создании записи.
"""
import logging
from django.conf import settings
import requests

logger = logging.getLogger(__name__)


def _send_telegram(chat_id, text: str) -> bool:
    """Отправить сообщение в Telegram (chat_id — число или строка). Возвращает True при успехе."""
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or ''
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN не задан — сообщение не отправлено")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.exception("Ошибка отправки в Telegram: %s", e)
        return False


def send_telegram_to_client(telegram_id: int, text: str) -> bool:
    """Отправить сообщение клиенту в Telegram."""
    return _send_telegram(telegram_id, text)


def _booking_base_info(booking):
    """Общие данные записи для текста сообщения."""
    time_str = booking.booking_time.strftime('%H:%M') if booking.booking_time else '—'
    end_str = booking.booking_end_time.strftime('%H:%M') if booking.booking_end_time else ''
    slot = f"{time_str}" + (f" – {end_str}" if end_str else "")
    service_name = booking.service.name if booking.service_id else "Консультация"
    duration = ""
    if booking.service_id and getattr(booking.service, 'duration_minutes', None):
        duration = f", {booking.service.duration_minutes} мин"
    calendar_name = getattr(booking.calendar, 'name', '') or '—'
    consultant_name = "—"
    if getattr(booking.calendar, 'consultant', None):
        c = booking.calendar.consultant
        consultant_name = f"{getattr(c, 'first_name', '')} {getattr(c, 'last_name', '')}".strip() or getattr(c, 'email', '') or consultant_name
    return {
        'service_name': service_name,
        'date_str': booking.booking_date.strftime('%d.%m.%Y'),
        'slot': slot,
        'duration': duration,
        'calendar_name': calendar_name,
        'consultant_name': consultant_name,
    }


def format_reminder_message(booking, hours_ahead: int) -> str:
    """Текст напоминания клиенту о консультации (время, услуга, специалист, место, длительность)."""
    info = _booking_base_info(booking)
    if hours_ahead >= 24:
        return (
            f"📅 <b>Напоминание о консультации</b>\n\n"
            f"Через 24 часа у вас запланирована консультация:\n\n"
            f"📌 Услуга: {info['service_name']}{info['duration']}\n"
            f"📅 Дата: {info['date_str']}\n"
            f"🕐 Время: {info['slot']}\n"
            f"👤 Специалист: {info['consultant_name']}\n"
            f"📍 Место: {info['calendar_name']}\n\n"
            f"До встречи!"
        )
    else:
        return (
            f"⏰ <b>Скоро консультация</b>\n\n"
            f"Через 1 час у вас запланирована консультация:\n\n"
            f"📌 Услуга: {info['service_name']}{info['duration']}\n"
            f"📅 Дата: {info['date_str']}\n"
            f"🕐 Время: {info['slot']}\n"
            f"👤 Специалист: {info['consultant_name']}\n"
            f"📍 Место: {info['calendar_name']}\n\n"
            f"Ждём вас!"
        )


def format_new_booking_message_for_specialist(booking) -> str:
    """Текст уведомления специалисту о новой записи."""
    info = _booking_base_info(booking)
    contact = []
    if getattr(booking, 'client_phone', None) and booking.client_phone:
        contact.append(f"📞 {booking.client_phone}")
    if getattr(booking, 'client_telegram', None) and booking.client_telegram:
        contact.append(f"✈️ {booking.client_telegram}")
    if getattr(booking, 'client_email', None) and booking.client_email:
        contact.append(f"📧 {booking.client_email}")
    contact_str = "\n".join(contact) if contact else "—"
    return (
        f"🆕 <b>Новая запись</b>\n\n"
        f"👤 Клиент: {getattr(booking, 'client_name', '') or '—'}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n\n"
        f"<b>Контакты:</b>\n{contact_str}"
    )


def format_client_booked_message(booking) -> str:
    """Текст клиенту «Вы записаны» (при создании записи, если telegram уже привязан)."""
    info = _booking_base_info(booking)
    return (
        f"✅ <b>Вы записаны</b>\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}\n\n"
        f"Напоминания за сутки и за час придут сюда."
    )


def notify_specialist_new_booking(booking) -> bool:
    """Отправить специалисту уведомление о новой записи в Telegram. Возвращает True при успехе."""
    try:
        consultant = getattr(booking.calendar, 'consultant', None)
        if not consultant:
            return False
        from consultant_menu.models import Integration
        integration = getattr(consultant, 'integration', None)
        if not integration or not getattr(integration, 'telegram_connected', False):
            return False
        chat_id = getattr(integration, 'telegram_chat_id', None) or ''
        if not str(chat_id).strip():
            return False
        text = format_new_booking_message_for_specialist(booking)
        return _send_telegram(chat_id.strip(), text)
    except Exception as e:
        logger.exception("Ошибка уведомления специалисту: %s", e)
        return False
