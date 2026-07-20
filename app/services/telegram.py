import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, Integration

logger = logging.getLogger(__name__)
settings = get_settings()
TIMEZONE_STR = "Europe/Moscow"


def _send_telegram(chat_id, text: str, bot_token: str | None = None) -> bool:
    token = (bot_token or "").strip() or settings.telegram_bot_token
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=data, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.exception("Telegram send error: %s", e)
        return False


def _integration_bot_token(integration: Integration | None) -> str | None:
    if not integration:
        return None
    token = (integration.telegram_bot_token or "").strip()
    return token or None


def send_telegram_to_client(telegram_id: int, text: str) -> bool:
    return _send_telegram(telegram_id, text)


def _booking_base_info(booking: Booking) -> dict:
    time_str = booking.booking_time.strftime("%H:%M") if booking.booking_time else "—"
    end_str = booking.booking_end_time.strftime("%H:%M") if booking.booking_end_time else ""
    slot = f"{time_str}" + (f" – {end_str}" if end_str else "")
    service_name = booking.service.name if booking.service else "Консультация"
    duration = ""
    if booking.service and booking.service.duration_minutes:
        duration = f", {booking.service.duration_minutes} мин"
    calendar_name = booking.calendar.name if booking.calendar else "—"
    consultant_name = "—"
    if booking.calendar and booking.calendar.consultant:
        c = booking.calendar.consultant
        consultant_name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email or consultant_name
    return {
        "service_name": service_name,
        "date_str": booking.booking_date.strftime("%d.%m.%Y"),
        "slot": slot,
        "duration": duration,
        "calendar_name": calendar_name,
        "consultant_name": consultant_name,
    }


def format_reminder_message(booking: Booking, hours_ahead: int) -> str:
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


def _telegram_link(username: str) -> str:
    u = (username or "").strip().lstrip("@").split("/")[-1].split("?")[0]
    return f"https://t.me/{u}" if u else ""


def format_new_booking_message_for_specialist(booking: Booking) -> str:
    info = _booking_base_info(booking)
    contact = []
    if booking.client_phone:
        contact.append(f"📞 {booking.client_phone}")
    telegram_raw = booking.client_telegram or ""
    if telegram_raw.strip():
        link = _telegram_link(telegram_raw)
        contact.append(f"✈️ Telegram: {link}" if link else f"✈️ {telegram_raw}")
    if booking.client_email:
        contact.append(f"📧 {booking.client_email}")
    contact_str = "\n".join(contact) if contact else "—"
    status_note = "\n⏳ Данные ждут подтверждения (клиент может подтвердить Телеграм на странице после записи)."
    return (
        f"🆕 <b>Новая запись</b>\n\n"
        f"👤 Клиент: {booking.client_name or '—'}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n\n"
        f"<b>Контакты:</b>\n{contact_str}"
        f"{status_note}"
    )


def format_client_booked_message(booking: Booking) -> str:
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


def format_specialist_reminder_message(booking: Booking, hours_ahead: int) -> str:
    info = _booking_base_info(booking)
    client_contact = []
    if booking.client_phone:
        client_contact.append(booking.client_phone)
    if booking.client_telegram:
        client_contact.append(booking.client_telegram)
    contact_str = ", ".join(client_contact) if client_contact else "—"
    if hours_ahead >= 24:
        return (
            f"📅 <b>Напоминание: консультация через 24 часа</b>\n\n"
            f"👤 Клиент: {booking.client_name or '—'}\n"
            f"📌 Услуга: {info['service_name']}{info['duration']}\n"
            f"📅 Дата: {info['date_str']}\n"
            f"🕐 Время: {info['slot']}\n"
            f"📍 Календарь: {info['calendar_name']}\n"
            f"📞 Контакт: {contact_str}"
        )
    return (
        f"⏰ <b>Через 1 час — консультация</b>\n\n"
        f"👤 Клиент: {booking.client_name or '—'}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n"
        f"📞 Контакт: {contact_str}"
    )


STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
    "completed": "Завершена",
}


def format_booking_status_changed_client(booking: Booking, new_status: str, old_status: str | None = None) -> str:
    info = _booking_base_info(booking)
    new_label = STATUS_LABELS.get(new_status, new_status)
    if old_status:
        old_label = STATUS_LABELS.get(old_status, old_status)
        status_line = f"Статус изменён: <b>{old_label}</b> → <b>{new_label}</b>"
    else:
        status_line = f"Статус: <b>{new_label}</b>"
    return (
        f"📋 <b>Изменение записи</b>\n\n"
        f"{status_line}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}"
    )


def format_booking_status_changed_specialist(booking: Booking, new_status: str, old_status: str | None = None) -> str:
    info = _booking_base_info(booking)
    new_label = STATUS_LABELS.get(new_status, new_status)
    if old_status:
        old_label = STATUS_LABELS.get(old_status, old_status)
        status_line = f"Статус: <b>{old_label}</b> → <b>{new_label}</b>"
    else:
        status_line = f"Статус: <b>{new_label}</b>"
    contact = []
    if booking.client_phone:
        contact.append(booking.client_phone)
    if booking.client_telegram:
        contact.append(booking.client_telegram)
    contact_str = ", ".join(contact) if contact else "—"
    return (
        f"📋 <b>Запись обновлена</b>\n\n"
        f"👤 Клиент: {booking.client_name or '—'}\n"
        f"{status_line}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📞 Контакт: {contact_str}"
    )


def notify_booking_status_changed(db: Session, booking: Booking, old_status: str | None = None) -> None:
    new_status = booking.status or ""
    if not new_status or new_status == "completed":
        return
    try:
        if booking.telegram_id:
            text_client = format_booking_status_changed_client(booking, new_status, old_status)
            _send_telegram(booking.telegram_id, text_client)
        consultant = booking.calendar.consultant if booking.calendar else None
        if consultant and consultant.integration and consultant.integration.telegram_chat_id:
            chat_id = (consultant.integration.telegram_chat_id or "").strip()
            if chat_id:
                text_spec = format_booking_status_changed_specialist(booking, new_status, old_status)
                _send_telegram(chat_id, text_spec, _integration_bot_token(consultant.integration))
    except Exception as e:
        logger.exception("Status change notification error: %s", e)


def notify_specialist_new_booking(booking: Booking) -> bool:
    try:
        consultant = booking.calendar.consultant if booking.calendar else None
        if not consultant:
            return False
        integration = consultant.integration
        if not integration or not integration.telegram_connected:
            return False
        chat_id = (integration.telegram_chat_id or "").strip()
        if not chat_id:
            return False
        text = format_new_booking_message_for_specialist(booking)
        return _send_telegram(chat_id, text, _integration_bot_token(integration))
    except Exception as e:
        logger.exception("New booking notification error: %s", e)
        return False


def on_booking_created(db: Session, booking: Booking) -> None:
    notify_specialist_new_booking(booking)
    if booking.telegram_id:
        send_telegram_to_client(booking.telegram_id, format_client_booked_message(booking))
    from app.services.google_calendar import sync_booking_to_google

    sync_booking_to_google(db, booking, created=True)


def on_booking_updated(db: Session, booking: Booking, created: bool = False) -> None:
    from app.services.google_calendar import sync_booking_to_google

    sync_booking_to_google(db, booking, created=created)


def send_reminders(db: Session) -> dict:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    sent = {"client_24": 0, "client_1": 0, "spec_24": 0, "spec_1": 0}

    bookings = (
        db.query(Booking)
        .filter(Booking.status.in_(["pending", "confirmed"]), Booking.booking_date >= now.date())
        .all()
    )

    for booking in bookings:
        if not booking.booking_time:
            continue
        booking_dt = datetime.combine(booking.booking_date, booking.booking_time, tzinfo=tz)
        delta_minutes = (booking_dt - now).total_seconds() / 60
        if delta_minutes <= 0:
            continue

        specialist_chat_id = None
        specialist_bot_token = None
        if booking.calendar and booking.calendar.consultant and booking.calendar.consultant.integration:
            integration = booking.calendar.consultant.integration
            if integration.telegram_connected:
                specialist_chat_id = (integration.telegram_chat_id or "").strip()
                specialist_bot_token = _integration_bot_token(integration)

        h1 = booking.calendar.reminder_hours_first if booking.calendar else 24
        h2 = booking.calendar.reminder_hours_second if booking.calendar else 1
        win = 30
        in_first = (h1 * 60 - win) <= delta_minutes <= (h1 * 60 + win)
        in_second = (h2 * 60 - win) <= delta_minutes <= (h2 * 60 + win)

        if in_first:
            if booking.telegram_id and not booking.reminder_24h_sent:
                if send_telegram_to_client(booking.telegram_id, format_reminder_message(booking, h1)):
                    booking.reminder_24h_sent = True
                    sent["client_24"] += 1
            if specialist_chat_id and not booking.specialist_reminder_24h_sent:
                if _send_telegram(specialist_chat_id, format_specialist_reminder_message(booking, h1), specialist_bot_token):
                    booking.specialist_reminder_24h_sent = True
                    sent["spec_24"] += 1

        if in_second:
            if booking.telegram_id and not booking.reminder_1h_sent:
                if send_telegram_to_client(booking.telegram_id, format_reminder_message(booking, h2)):
                    booking.reminder_1h_sent = True
                    sent["client_1"] += 1
            if specialist_chat_id and not booking.specialist_reminder_1h_sent:
                if _send_telegram(specialist_chat_id, format_specialist_reminder_message(booking, h2), specialist_bot_token):
                    booking.specialist_reminder_1h_sent = True
                    sent["spec_1"] += 1

    db.commit()
    return sent
