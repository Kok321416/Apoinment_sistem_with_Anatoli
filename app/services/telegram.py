import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Booking, Calendar, Consultant, Integration

logger = logging.getLogger(__name__)
settings = get_settings()
TIMEZONE_STR = "Europe/Moscow"

_tg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-send")


def _norm_chat_id(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def same_telegram_chat(a, b) -> bool:
    """True when two chat ids refer to the same Telegram chat."""
    na, nb = _norm_chat_id(a), _norm_chat_id(b)
    return bool(na and nb and na == nb)


def notify_dedup_enabled() -> bool:
    return bool(getattr(settings, "notify_dedup", False))


def _specialist_chat_for_booking(booking: Booking) -> tuple[str | None, str | None]:
    """Return (chat_id, bot_token) for specialist notifications, or (None, None)."""
    consultant = booking.calendar.consultant if booking.calendar else None
    integration = consultant.integration if consultant else None
    if not _integration_notifications_on(integration):
        return None, None
    chat_id = (integration.telegram_chat_id or "").strip() or None
    return chat_id, _integration_bot_token(integration)


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


def send_telegram_async(chat_id, text: str, bot_token: str | None = None) -> None:
    """Fire-and-forget send so FastAPI event loop is not blocked."""
    _tg_executor.submit(_send_telegram, chat_id, text, bot_token)


def _integration_bot_token(integration: Integration | None) -> str | None:
    if not integration:
        return None
    token = (integration.telegram_bot_token or "").strip()
    return token or None


def _integration_notifications_on(integration: Integration | None) -> bool:
    if not integration:
        return False
    if not integration.telegram_connected:
        return False
    if integration.telegram_enabled is False:
        return False
    return bool((integration.telegram_chat_id or "").strip())


def send_telegram_to_client(telegram_id: int, text: str) -> bool:
    return _send_telegram(telegram_id, text)


def _hours_label(hours: int) -> str:
    hours = int(hours or 0)
    if hours <= 0:
        return "скоро"
    if hours == 1:
        return "1 час"
    if 2 <= hours <= 4:
        return f"{hours} часа"
    if hours % 10 == 1 and hours % 100 != 11:
        return f"{hours} час"
    if 2 <= hours % 10 <= 4 and not (12 <= hours % 100 <= 14):
        return f"{hours} часа"
    return f"{hours} часов"


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
    label = _hours_label(hours_ahead)
    return (
        f"📅 <b>Ваша запись: напоминание</b>\n\n"
        f"Через {label} у вас запланирована консультация:\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}\n\n"
        f"До встречи!"
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
        f"🆕 <b>К вам новая запись</b>\n\n"
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
        f"✅ <b>Ваша запись подтверждена</b>\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}\n\n"
        f"Напоминания придут сюда перед консультацией."
    )


def format_specialist_reminder_message(booking: Booking, hours_ahead: int) -> str:
    info = _booking_base_info(booking)
    client_contact = []
    if booking.client_phone:
        client_contact.append(booking.client_phone)
    if booking.client_telegram:
        client_contact.append(booking.client_telegram)
    contact_str = ", ".join(client_contact) if client_contact else "—"
    label = _hours_label(hours_ahead)
    return (
        f"📅 <b>К вам запись: напоминание через {label}</b>\n\n"
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
        f"📋 <b>Ваша запись: изменение статуса</b>\n\n"
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
        f"📋 <b>К вам запись: статус обновлён</b>\n\n"
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
        specialist_chat_id, specialist_token = _specialist_chat_for_booking(booking)
        client_chat = booking.telegram_id
        skip_client = notify_dedup_enabled() and same_telegram_chat(client_chat, specialist_chat_id)

        if client_chat and not skip_client:
            text_client = format_booking_status_changed_client(booking, new_status, old_status)
            send_telegram_async(client_chat, text_client)
        if specialist_chat_id:
            text_spec = format_booking_status_changed_specialist(booking, new_status, old_status)
            send_telegram_async(specialist_chat_id, text_spec, specialist_token)
    except Exception as e:
        logger.exception("Status change notification error: %s", e)


def notify_specialist_new_booking(booking: Booking) -> bool:
    try:
        chat_id, token = _specialist_chat_for_booking(booking)
        if not chat_id:
            return False
        text = format_new_booking_message_for_specialist(booking)
        return _send_telegram(chat_id, text, token)
    except Exception as e:
        logger.exception("New booking notification error: %s", e)
        return False


def on_booking_created(db: Session, booking: Booking) -> None:
    try:
        notify_specialist_new_booking(booking)
    except Exception:
        logger.exception("on_booking_created specialist notify failed")
    try:
        if booking.telegram_id:
            specialist_chat_id, _ = _specialist_chat_for_booking(booking)
            if notify_dedup_enabled() and same_telegram_chat(booking.telegram_id, specialist_chat_id):
                # Specialist already got "new booking"; skip duplicate client confirm to same chat
                pass
            else:
                send_telegram_async(booking.telegram_id, format_client_booked_message(booking))
    except Exception:
        logger.exception("on_booking_created client notify failed")
    try:
        from app.services.google_calendar import sync_booking_to_google

        sync_booking_to_google(db, booking, created=True)
    except Exception:
        logger.exception("on_booking_created google sync failed")


def on_booking_updated(db: Session, booking: Booking, created: bool = False) -> None:
    try:
        from app.services.google_calendar import sync_booking_to_google

        sync_booking_to_google(db, booking, created=created)
    except Exception:
        logger.exception("on_booking_updated google sync failed")


def send_reminders(db: Session) -> dict:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    sent = {"client_24": 0, "client_1": 0, "spec_24": 0, "spec_1": 0}
    horizon = now.date() + timedelta(days=14)

    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar)
            .joinedload(Calendar.consultant)
            .joinedload(Consultant.integration),
        )
        .filter(
            Booking.status.in_(["pending", "confirmed"]),
            Booking.booking_date >= now.date(),
            Booking.booking_date <= horizon,
        )
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
        integration = None
        if booking.calendar and booking.calendar.consultant:
            integration = booking.calendar.consultant.integration
        if _integration_notifications_on(integration):
            specialist_chat_id = (integration.telegram_chat_id or "").strip()
            specialist_bot_token = _integration_bot_token(integration)

        h1 = booking.calendar.reminder_hours_first if booking.calendar else 24
        h2 = booking.calendar.reminder_hours_second if booking.calendar else 1
        win = 30
        in_first = (h1 * 60 - win) <= delta_minutes <= (h1 * 60 + win)
        in_second = (h2 * 60 - win) <= delta_minutes <= (h2 * 60 + win)

        if in_first:
            if booking.telegram_id and not booking.reminder_24h_sent:
                skip_client = notify_dedup_enabled() and same_telegram_chat(
                    booking.telegram_id, specialist_chat_id
                )
                if not skip_client:
                    if send_telegram_to_client(booking.telegram_id, format_reminder_message(booking, h1)):
                        booking.reminder_24h_sent = True
                        sent["client_24"] += 1
                else:
                    # Mark sent so we do not retry forever when dedup skips duplicate
                    booking.reminder_24h_sent = True
            if specialist_chat_id and not booking.specialist_reminder_24h_sent:
                if _send_telegram(specialist_chat_id, format_specialist_reminder_message(booking, h1), specialist_bot_token):
                    booking.specialist_reminder_24h_sent = True
                    sent["spec_24"] += 1

        if in_second:
            if booking.telegram_id and not booking.reminder_1h_sent:
                skip_client = notify_dedup_enabled() and same_telegram_chat(
                    booking.telegram_id, specialist_chat_id
                )
                if not skip_client:
                    if send_telegram_to_client(booking.telegram_id, format_reminder_message(booking, h2)):
                        booking.reminder_1h_sent = True
                        sent["client_1"] += 1
                else:
                    booking.reminder_1h_sent = True
            if specialist_chat_id and not booking.specialist_reminder_1h_sent:
                if _send_telegram(specialist_chat_id, format_specialist_reminder_message(booking, h2), specialist_bot_token):
                    booking.specialist_reminder_1h_sent = True
                    sent["spec_1"] += 1

    db.commit()
    return sent
