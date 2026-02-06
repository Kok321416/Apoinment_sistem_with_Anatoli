"""
Синхронизация записей (Booking) с Google Calendar специалиста.
Используется Integration специалиста (google_refresh_token, google_calendar_id).
При создании/обновлении/отмене записи — создаётся/обновляется/удаляется событие в календаре.
"""
import logging
from datetime import datetime, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEZONE_STR = "Europe/Moscow"


def _get_calendar_service(integration):
    """Возвращает сервис Google Calendar API или None."""
    if not integration or not (getattr(integration, "google_refresh_token", None) or "").strip():
        return None
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "") or ""
    client_secret = getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "") or ""
    if not client_id or not client_secret:
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request

        creds = Credentials(
            token=None,
            refresh_token=integration.google_refresh_token.strip(),
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=getattr(settings, "GOOGLE_CALENDAR_SCOPES", ["https://www.googleapis.com/auth/calendar.events"]),
        )
        creds.refresh(Request())
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.warning("consultant_menu Google Calendar: не удалось создать service: %s", e)
        return None


def _booking_start_end(booking):
    """Возвращает (start_dt, end_dt) для записи (aware datetime при наличии timezone в settings)."""
    from django.utils import timezone as tz
    start_dt = datetime.combine(booking.booking_date, booking.booking_time)
    if booking.booking_end_time:
        end_dt = datetime.combine(booking.booking_date, booking.booking_end_time)
    else:
        duration = getattr(booking.service, "duration_minutes", None) or 60
        end_dt = start_dt + timedelta(minutes=duration)
    if tz.is_naive(start_dt) and getattr(tz, "get_current_timezone", None):
        current_tz = tz.get_current_timezone()
        if current_tz:
            start_dt = tz.make_aware(start_dt, current_tz)
            end_dt = tz.make_aware(end_dt, current_tz)
    return start_dt, end_dt


def create_booking_google_event(integration, booking):
    """
    Создаёт событие в Google Calendar специалиста по записи.
    Сохраняет google_event_id в booking. Возвращает True при успехе.
    """
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (getattr(integration, "google_calendar_id", None) or "").strip() or "primary"
    try:
        start_dt, end_dt = _booking_start_end(booking)
        event = {
            "summary": f"Консультация: {booking.client_name}",
            "description": (
                f"Услуга: {booking.service.name}\n"
                f"Телефон: {booking.client_phone or '-'}\n"
                f"Email: {booking.client_email or '-'}\n"
                f"Telegram: {booking.client_telegram or '-'}\n"
                f"{booking.notes or ''}"
            ).strip(),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            },
        }
        created = service.events().insert(calendarId=calendar_id, body=event).execute()
        event_id = created.get("id")
        if event_id:
            booking.google_event_id = event_id
            booking.save(update_fields=["google_event_id"])
            logger.info("consultant_menu Google Calendar: создано событие booking_id=%s event_id=%s", booking.pk, event_id)
            return True
    except Exception as e:
        logger.warning("consultant_menu Google Calendar: ошибка создания события: %s", e)
    return False


def update_booking_google_event(integration, booking):
    """Обновляет событие в Google Calendar. Если google_event_id нет — создаёт новое."""
    if not getattr(booking, "google_event_id", None) or not booking.google_event_id.strip():
        return create_booking_google_event(integration, booking)
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (getattr(integration, "google_calendar_id", None) or "").strip() or "primary"
    try:
        start_dt, end_dt = _booking_start_end(booking)
        event = {
            "summary": f"Консультация: {booking.client_name}",
            "description": (
                f"Услуга: {booking.service.name}\n"
                f"Телефон: {booking.client_phone or '-'}\n"
                f"Email: {booking.client_email or '-'}\n"
                f"Telegram: {booking.client_telegram or '-'}\n"
                f"{booking.notes or ''}"
            ).strip(),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE_STR},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE_STR},
        }
        service.events().update(
            calendarId=calendar_id,
            eventId=booking.google_event_id.strip(),
            body=event,
        ).execute()
        logger.info("consultant_menu Google Calendar: обновлено событие booking_id=%s", booking.pk)
        return True
    except Exception as e:
        logger.warning("consultant_menu Google Calendar: ошибка обновления события: %s", e)
    return False


def delete_booking_google_event(integration, booking, clear_event_id=True):
    """
    Удаляет событие из Google Calendar (при отмене/удалении записи).
    Если clear_event_id=True и запись ещё в БД — обнуляет google_event_id у booking.
    """
    event_id = (getattr(booking, "google_event_id", None) or "").strip()
    if not event_id:
        return True
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (getattr(integration, "google_calendar_id", None) or "").strip() or "primary"
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        if clear_event_id and getattr(booking, "pk", None):
            booking.google_event_id = None
            booking.save(update_fields=["google_event_id"])
        logger.info("consultant_menu Google Calendar: удалено событие booking_id=%s", getattr(booking, "pk", None))
        return True
    except Exception as e:
        logger.warning("consultant_menu Google Calendar: ошибка удаления события: %s", e)
    return False
