import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Booking, Calendar, Consultant, Integration
from app.services.telegram_copy import (
    STATUS_LABELS,
    format_booking_rescheduled_client,
    format_booking_rescheduled_specialist,
    format_booking_status_changed_client,
    format_booking_status_changed_specialist,
    format_client_booked_message,
    format_new_booking_message_for_specialist,
    format_reminder_message,
    format_specialist_reminder_message,
    booking_base_info as _booking_base_info,
)

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


def notify_booking_status_changed(db: Session, booking: Booking, old_status: str | None = None) -> None:
    new_status = booking.status or ""
    if not new_status or new_status == "completed":
        return
    try:
        specialist_chat_id, specialist_token = _specialist_chat_for_booking(booking)
        client_chat = booking.telegram_id
        skip_client = notify_dedup_enabled() and same_telegram_chat(client_chat, specialist_chat_id)
        if skip_client:
            from app.services.app_counters import record_notify_dedup_hit

            record_notify_dedup_hit(db)

        if client_chat and not skip_client:
            text_client = format_booking_status_changed_client(booking, new_status, old_status)
            send_telegram_async(client_chat, text_client)
        if specialist_chat_id:
            text_spec = format_booking_status_changed_specialist(booking, new_status, old_status)
            send_telegram_async(specialist_chat_id, text_spec, specialist_token)
    except Exception as e:
        logger.exception("Status change notification error: %s", e)


def notify_booking_rescheduled(
    db: Session,
    booking: Booking,
    *,
    old_date,
    old_time,
    old_end_time=None,
) -> None:
    try:
        specialist_chat_id, specialist_token = _specialist_chat_for_booking(booking)
        client_chat = booking.telegram_id
        skip_client = notify_dedup_enabled() and same_telegram_chat(client_chat, specialist_chat_id)
        if skip_client:
            from app.services.app_counters import record_notify_dedup_hit

            record_notify_dedup_hit(db)

        if client_chat and not skip_client:
            send_telegram_async(
                client_chat,
                format_booking_rescheduled_client(
                    booking, old_date=old_date, old_time=old_time, old_end_time=old_end_time
                ),
            )
        if specialist_chat_id:
            send_telegram_async(
                specialist_chat_id,
                format_booking_rescheduled_specialist(
                    booking, old_date=old_date, old_time=old_time, old_end_time=old_end_time
                ),
                specialist_token,
            )
    except Exception as e:
        logger.exception("Reschedule notification error: %s", e)


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
                from app.services.app_counters import record_notify_dedup_hit

                record_notify_dedup_hit(db)
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
                    from app.services.app_counters import record_notify_dedup_hit

                    record_notify_dedup_hit(db)
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
                    from app.services.app_counters import record_notify_dedup_hit

                    record_notify_dedup_hit(db)
                    booking.reminder_1h_sent = True
            if specialist_chat_id and not booking.specialist_reminder_1h_sent:
                if _send_telegram(specialist_chat_id, format_specialist_reminder_message(booking, h2), specialist_bot_token):
                    booking.specialist_reminder_1h_sent = True
                    sent["spec_1"] += 1

    db.commit()
    return sent
