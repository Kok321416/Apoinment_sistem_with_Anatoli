"""
Отправка уведомлений в Telegram: напоминания клиенту, уведомление специалисту о новой записи.
Используется management command send_booking_reminders и signal при создании записи.
"""
import logging
from django.conf import settings
import requests

logger = logging.getLogger(__name__)


def _send_telegram(chat_id, text: str, reply_markup: dict = None) -> bool:
    """Отправить сообщение в Telegram (chat_id — число или строка). reply_markup — опционально (inline_keyboard)."""
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
    if reply_markup:
        import json
        data['reply_markup'] = json.dumps(reply_markup)
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


def _telegram_link(username: str) -> str:
    """Ссылка на Telegram: t.me/username (без @)."""
    u = (username or "").strip().lstrip("@").split("/")[-1].split("?")[0]
    return f"https://t.me/{u}" if u else ""


def format_new_booking_message_for_specialist(booking) -> str:
    """Текст уведомления специалисту о новой записи (включая ссылку на Telegram клиента)."""
    info = _booking_base_info(booking)
    contact = []
    if getattr(booking, 'client_phone', None) and booking.client_phone:
        contact.append(f"📞 {booking.client_phone}")
    telegram_raw = getattr(booking, 'client_telegram', None) or ""
    if telegram_raw.strip():
        link = _telegram_link(telegram_raw)
        if link:
            contact.append(f"✈️ Telegram: {link}")
        else:
            contact.append(f"✈️ {telegram_raw}")
    if getattr(booking, 'client_email', None) and booking.client_email:
        contact.append(f"📧 {booking.client_email}")
    contact_str = "\n".join(contact) if contact else "—"
    status_note = "\n⏳ Данные ждут подтверждения (клиент может подтвердить Telegram на странице после записи)."
    return (
        f"🆕 <b>Новая запись</b>\n\n"
        f"👤 Клиент: {getattr(booking, 'client_name', '') or '—'}\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📍 Календарь: {info['calendar_name']}\n\n"
        f"<b>Контакты:</b>\n{contact_str}"
        f"{status_note}"
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


def format_specialist_reminder_message(booking, hours_ahead: int) -> str:
    """Текст напоминания специалисту о предстоящей консультации."""
    info = _booking_base_info(booking)
    client_contact = []
    if getattr(booking, 'client_phone', None) and booking.client_phone:
        client_contact.append(booking.client_phone)
    if getattr(booking, 'client_telegram', None) and booking.client_telegram:
        client_contact.append(booking.client_telegram)
    contact_str = ", ".join(client_contact) if client_contact else "—"
    if hours_ahead >= 24:
        return (
            f"📅 <b>Напоминание: консультация через 24 часа</b>\n\n"
            f"👤 Клиент: {getattr(booking, 'client_name', '') or '—'}\n"
            f"📌 Услуга: {info['service_name']}{info['duration']}\n"
            f"📅 Дата: {info['date_str']}\n"
            f"🕐 Время: {info['slot']}\n"
            f"📍 Календарь: {info['calendar_name']}\n"
            f"📞 Контакт: {contact_str}"
        )
    else:
        return (
            f"⏰ <b>Через 1 час — консультация</b>\n\n"
            f"👤 Клиент: {getattr(booking, 'client_name', '') or '—'}\n"
            f"📌 Услуга: {info['service_name']}{info['duration']}\n"
            f"📅 Дата: {info['date_str']}\n"
            f"🕐 Время: {info['slot']}\n"
            f"📍 Календарь: {info['calendar_name']}\n"
            f"📞 Контакт: {contact_str}"
        )


STATUS_LABELS = {
    'pending': 'Ожидает',
    'confirmed': 'Подтверждена',
    'cancelled': 'Отменена',
    'completed': 'Завершена',
}


def format_booking_status_changed_client(booking, new_status: str, old_status: str = None) -> str:
    """Текст клиенту об изменении статуса/записи."""
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


def format_booking_status_changed_specialist(booking, new_status: str, old_status: str = None) -> str:
    """Текст специалисту об изменении статуса записи (подтверждение/отмена/завершение)."""
    info = _booking_base_info(booking)
    new_label = STATUS_LABELS.get(new_status, new_status)
    if old_status:
        old_label = STATUS_LABELS.get(old_status, old_status)
        status_line = f"Статус: <b>{old_label}</b> → <b>{new_label}</b>"
    else:
        status_line = f"Статус: <b>{new_label}</b>"
    contact = []
    if getattr(booking, 'client_phone', None) and booking.client_phone:
        contact.append(booking.client_phone)
    if getattr(booking, 'client_telegram', None) and booking.client_telegram:
        contact.append(booking.client_telegram)
    contact_str = ", ".join(contact) if contact else "—"
    return (
        f"📋 <b>Запись обновлена</b>\n\n"
        f"👤 Клиент: {getattr(booking, 'client_name', '') or '—'}\n"
        f"{status_line}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"📅 Дата: {info['date_str']}\n"
        f"🕐 Время: {info['slot']}\n"
        f"📞 Контакт: {contact_str}"
    )


def format_booking_rescheduled_client(booking, old_date_str: str, old_slot: str) -> str:
    """Текст клиенту о переносе консультации на другое время."""
    info = _booking_base_info(booking)
    return (
        f"📅 <b>Время консультации перенесено</b>\n\n"
        f"Было: {old_date_str}, {old_slot}\n"
        f"Стало: {info['date_str']}, {info['slot']}\n\n"
        f"📌 Услуга: {info['service_name']}{info['duration']}\n"
        f"👤 Специалист: {info['consultant_name']}\n"
        f"📍 Место: {info['calendar_name']}"
    )


def notify_booking_rescheduled(booking, old_date, old_time, old_end_time) -> None:
    """Отправить клиенту в Telegram уведомление о переносе времени консультации."""
    from datetime import date, time
    if isinstance(old_date, date):
        old_date_str = old_date.strftime('%d.%m.%Y')
    else:
        old_date_str = str(old_date)
    old_t = old_time.strftime('%H:%M') if hasattr(old_time, 'strftime') else str(old_time)
    old_e = old_end_time.strftime('%H:%M') if old_end_time and hasattr(old_end_time, 'strftime') else ''
    old_slot = old_t + (f' – {old_e}' if old_e else '')
    try:
        telegram_id = getattr(booking, 'telegram_id', None)
        if telegram_id:
            text = format_booking_rescheduled_client(booking, old_date_str, old_slot)
            _send_telegram(telegram_id, text)
    except Exception as e:
        logger.exception("Ошибка уведомления о переносе записи: %s", e)


def notify_booking_status_changed(booking, old_status: str = None) -> None:
    """
    Отправить клиенту и специалисту уведомления об изменении записи (статус и т.д.).
    Вызывать после сохранения записи (например при смене статуса на сайте).
    При смене на «завершена» уведомления не отправляются (завершение по истечении времени).
    """
    new_status = getattr(booking, 'status', None) or ''
    if not new_status or new_status == 'completed':
        return
    try:
        # Клиенту — если привязан Telegram
        telegram_id = getattr(booking, 'telegram_id', None)
        if telegram_id:
            text_client = format_booking_status_changed_client(booking, new_status, old_status)
            _send_telegram(telegram_id, text_client)
        # Специалисту
        consultant = getattr(booking.calendar, 'consultant', None)
        if consultant:
            from consultant_menu.models import Integration
            try:
                integration = consultant.integration
            except Exception:
                integration = None
            if integration and getattr(integration, 'telegram_chat_id', None):
                chat_id = (integration.telegram_chat_id or '').strip()
                if chat_id:
                    text_spec = format_booking_status_changed_specialist(booking, new_status, old_status)
                    _send_telegram(chat_id, text_spec)
    except Exception as e:
        logger.exception("Ошибка уведомления об изменении записи: %s", e)


def notify_specialist_new_booking(booking) -> bool:
    """Отправить специалисту уведомление о новой записи в Telegram с кнопками «Подтвердить» / «Отклонить»."""
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
        text = (
            "🆕 <b>Вам новая запись</b>\n\n"
            + format_new_booking_message_for_specialist(booking).replace("🆕 <b>Новая запись</b>\n\n", "", 1)
            + "\n\n<b>Подтвердить или отклонить?</b>"
        )
        reply_markup = {
            'inline_keyboard': [
                [
                    {'text': '✅ Подтвердить', 'callback_data': f'spec_bok_ok_{booking.id}'},
                    {'text': '❌ Отклонить', 'callback_data': f'spec_bok_no_{booking.id}'},
                ],
            ]
        }
        return _send_telegram(chat_id.strip(), text, reply_markup)
    except Exception as e:
        logger.exception("Ошибка уведомления специалисту: %s", e)
        return False
