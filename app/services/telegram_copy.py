"""Canonical Telegram transactional + broadcast copy (Phase 11).

Style rules:
- First line: role/type title (Ваша запись / К вам запись / Новости)
- Short paragraphs; emoji budget ~1-2 per message header
- No em/en dashes - use hyphen "-"
- User-provided fields HTML-escaped for parse_mode=HTML
"""
from __future__ import annotations

import html
import re
from typing import Any

from app.models import Booking

STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
    "completed": "Завершена",
}

# Forbidden dash characters (em, en, figure, horizontal bar, minus sign variants in copy)
_DASH_RE = re.compile(r"[\u2012\u2013\u2014\u2015\u2212]")


def tg_escape(value: Any) -> str:
    """Escape text for Telegram HTML parse_mode."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def normalize_dashes(text: str) -> str:
    """Replace long dashes with ASCII hyphen."""
    return _DASH_RE.sub("-", text or "")


def assert_no_long_dashes(text: str) -> bool:
    return not bool(_DASH_RE.search(text or ""))


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


def _telegram_link(username: str) -> str:
    u = (username or "").strip().lstrip("@").split("/")[-1].split("?")[0]
    return f"https://t.me/{u}" if u else ""


def booking_base_info(booking: Booking) -> dict[str, str]:
    """Escaped booking fields for templates."""
    time_str = booking.booking_time.strftime("%H:%M") if booking.booking_time else "-"
    end_str = booking.booking_end_time.strftime("%H:%M") if booking.booking_end_time else ""
    slot = f"{time_str}" + (f" - {end_str}" if end_str else "")
    service_name = booking.service.name if booking.service else "Консультация"
    duration = ""
    if booking.service and booking.service.duration_minutes:
        duration = f", {booking.service.duration_minutes} мин"
    calendar_name = booking.calendar.name if booking.calendar else "-"
    consultant_name = "-"
    if booking.calendar and booking.calendar.consultant:
        c = booking.calendar.consultant
        consultant_name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email or consultant_name
    date_str = booking.booking_date.strftime("%d.%m.%Y") if booking.booking_date else "-"
    return {
        "service_name": tg_escape(service_name),
        "date_str": tg_escape(date_str),
        "slot": tg_escape(slot),
        "duration": tg_escape(duration),
        "calendar_name": tg_escape(calendar_name),
        "consultant_name": tg_escape(consultant_name),
        "client_name": tg_escape(booking.client_name or "-"),
    }


def _fmt_dt(d, t) -> str:
    ds = d.strftime("%d.%m.%Y") if d else "-"
    ts = t.strftime("%H:%M") if t else "-"
    return f"{ds} {ts}"


def format_reminder_message(booking: Booking, hours_ahead: int) -> str:
    info = booking_base_info(booking)
    label = _hours_label(hours_ahead)
    return (
        f"📅 <b>Ваша запись: напоминание</b>\n\n"
        f"Через {label} у вас консультация.\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}"
    )


def format_specialist_reminder_message(booking: Booking, hours_ahead: int) -> str:
    info = booking_base_info(booking)
    contact = []
    if booking.client_phone:
        contact.append(tg_escape(booking.client_phone))
    if booking.client_telegram:
        contact.append(tg_escape(booking.client_telegram))
    contact_str = ", ".join(contact) if contact else "-"
    label = _hours_label(hours_ahead)
    return (
        f"📅 <b>К вам запись: напоминание через {label}</b>\n\n"
        f"👤 Клиент: {info['client_name']}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n"
        f"📞 Контакт: {contact_str}"
    )


def format_new_booking_message_for_specialist(booking: Booking) -> str:
    info = booking_base_info(booking)
    contact = []
    if booking.client_phone:
        contact.append(f"📞 {tg_escape(booking.client_phone)}")
    telegram_raw = booking.client_telegram or ""
    if telegram_raw.strip():
        link = _telegram_link(telegram_raw)
        if link:
            contact.append(f'✈️ Telegram: <a href="{tg_escape(link)}">{tg_escape(telegram_raw.strip())}</a>')
        else:
            contact.append(f"✈️ {tg_escape(telegram_raw)}")
    if booking.client_email:
        contact.append(f"📧 {tg_escape(booking.client_email)}")
    contact_str = "\n".join(contact) if contact else "-"
    return (
        f"🆕 <b>К вам новая запись</b>\n\n"
        f"👤 Клиент: {info['client_name']}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n\n"
        f"<b>Контакты</b>\n{contact_str}\n\n"
        f"⏳ Клиент может подтвердить Телеграм на странице после записи."
    )


def format_client_booked_message(booking: Booking, *, channel: str = "telegram") -> str:
    info = booking_base_info(booking)
    if channel == "email":
        footer = "Напоминания придут на эту почту перед консультацией."
    elif channel == "vk":
        footer = "Напоминания придут сюда в сообщениях VK перед консультацией."
    else:
        footer = "Напоминания придут сюда перед консультацией."
    return (
        f"✅ <b>Ваша запись подтверждена</b>\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}\n\n"
        f"{footer}"
    )


def format_booking_status_changed_client(
    booking: Booking, new_status: str, old_status: str | None = None
) -> str:
    info = booking_base_info(booking)
    new_label = STATUS_LABELS.get(new_status, new_status)
    if old_status:
        old_label = STATUS_LABELS.get(old_status, old_status)
        status_line = f"Статус: <b>{tg_escape(old_label)}</b> -> <b>{tg_escape(new_label)}</b>"
    else:
        status_line = f"Статус: <b>{tg_escape(new_label)}</b>"
    return (
        f"📋 <b>Ваша запись: изменение статуса</b>\n\n"
        f"{status_line}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}"
    )


def format_booking_status_changed_specialist(
    booking: Booking, new_status: str, old_status: str | None = None
) -> str:
    info = booking_base_info(booking)
    new_label = STATUS_LABELS.get(new_status, new_status)
    if old_status:
        old_label = STATUS_LABELS.get(old_status, old_status)
        status_line = f"Статус: <b>{tg_escape(old_label)}</b> -> <b>{tg_escape(new_label)}</b>"
    else:
        status_line = f"Статус: <b>{tg_escape(new_label)}</b>"
    contact = []
    if booking.client_phone:
        contact.append(tg_escape(booking.client_phone))
    if booking.client_telegram:
        contact.append(tg_escape(booking.client_telegram))
    contact_str = ", ".join(contact) if contact else "-"
    return (
        f"📋 <b>К вам запись: статус обновлён</b>\n\n"
        f"👤 Клиент: {info['client_name']}\n"
        f"{status_line}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📞 Контакт: {contact_str}"
    )


def format_booking_rescheduled_client(booking: Booking, *, old_date, old_time, old_end_time=None) -> str:
    info = booking_base_info(booking)
    old_slot = _fmt_dt(old_date, old_time)
    if old_end_time:
        old_slot = f"{old_slot} - {old_end_time.strftime('%H:%M')}"
    return (
        f"📅 <b>Ваша запись: перенесена</b>\n\n"
        f"Было: {tg_escape(old_slot)}\n"
        f"Стало: {info['date_str']} {info['slot']}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}"
    )


def format_booking_rescheduled_specialist(
    booking: Booking, *, old_date, old_time, old_end_time=None
) -> str:
    info = booking_base_info(booking)
    old_slot = _fmt_dt(old_date, old_time)
    if old_end_time:
        old_slot = f"{old_slot} - {old_end_time.strftime('%H:%M')}"
    return (
        f"📅 <b>К вам запись: перенесена</b>\n\n"
        f"👤 Клиент: {info['client_name']}\n"
        f"Было: {tg_escape(old_slot)}\n"
        f"Стало: {info['date_str']} {info['slot']}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📍 Календарь: {info['calendar_name']}"
    )


def format_broadcast_message(body: str) -> str:
    """Wrap admin broadcast body with canonical news header if missing."""
    text = normalize_dashes((body or "").strip())
    if not text:
        return ""
    if text.startswith("📢"):
        return text
    return f"📢 <b>Новости сервиса</b>\n\n{text}"


def sample_template_previews() -> list[dict[str, str]]:
    """Static samples for admin Telegram Center (no DB)."""
    return [
        {
            "key": "client_booked",
            "title": "Клиент: запись подтверждена",
            "text": (
                "✅ <b>Ваша запись подтверждена</b>\n\n"
                "📌 Услуга: Консультация, 60 мин\n"
                "📅 Дата: 22.07.2026\n"
                "🕐 Время: 15:00 - 16:00\n"
                "👤 Специалист: Иван П.\n"
                "📍 Место: Основной"
            ),
        },
        {
            "key": "specialist_new",
            "title": "Специалист: новая запись",
            "text": (
                "🆕 <b>К вам новая запись</b>\n\n"
                "👤 Клиент: Анна\n"
                "📌 Услуга: Консультация, 60 мин\n"
                "📅 Дата: 22.07.2026\n"
                "🕐 Время: 15:00 - 16:00\n"
                "📍 Календарь: Основной"
            ),
        },
        {
            "key": "client_reminder",
            "title": "Клиент: напоминание",
            "text": (
                "📅 <b>Ваша запись: напоминание</b>\n\n"
                "Через 6 часов у вас консультация.\n\n"
                "📌 Услуга: Консультация\n"
                "📅 Дата: 22.07.2026\n"
                "🕐 Время: 15:00"
            ),
        },
        {
            "key": "broadcast",
            "title": "Рассылка",
            "text": (
                "📢 <b>Новости сервиса</b>\n\n"
                "Обновили запись в Telegram: сайт открывается прямо в приложении."
            ),
        },
    ]
