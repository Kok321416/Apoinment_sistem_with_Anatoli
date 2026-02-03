"""
Утилита для синхронизации записей с Google Calendar.
Создание/обновление/удаление событий при создании/изменении/отмене записи.
"""
import logging
from datetime import timedelta

from django.conf import settings

logger = logging.getLogger(__name__)


def get_calendar_service(specialist):
    """
    Возвращает объект service для Google Calendar API или None, если токен не настроен.
    """
    if not specialist.google_refresh_token:
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
            refresh_token=specialist.google_refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=getattr(settings, "GOOGLE_CALENDAR_SCOPES", ["https://www.googleapis.com/auth/calendar.events"]),
        )
        creds.refresh(Request())
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.warning("Google Calendar: не удалось создать service: %s", e)
        return None


def create_google_calendar_event(specialist, appointment):
    """
    Создаёт событие в Google Calendar специалиста и сохраняет google_event_id в appointment.
    Возвращает True при успехе, False при ошибке или отсутствии токена.
    """
    service = get_calendar_service(specialist)
    if not service:
        return False
    calendar_id = specialist.google_calendar_id or "primary"
    try:
        start_dt = appointment.appointment_date
        end_dt = start_dt + timedelta(minutes=appointment.duration or 60)
        # RFC3339 для API
        timezone_str = "Europe/Moscow"
        event = {
            "summary": f"Консультация: {appointment.client_name}",
            "description": (
                f"Email: {appointment.client_email}\n"
                f"Телефон: {appointment.client_phone or '-'}\n"
                f"Telegram: {appointment.client_telegram or '-'}\n"
                f"{appointment.notes or ''}"
            ).strip(),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": timezone_str,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": timezone_str,
            },
        }
        created = service.events().insert(calendarId=calendar_id, body=event).execute()
        event_id = created.get("id")
        if event_id:
            appointment.google_event_id = event_id
            appointment.save(update_fields=["google_event_id"])
            return True
    except Exception as e:
        logger.warning("Google Calendar: ошибка создания события: %s", e)
    return False


def update_google_calendar_event(specialist, appointment):
    """
    Обновляет событие в Google Calendar (время, статус и т.д.).
    Если google_event_id нет — создаёт новое событие.
    """
    if not appointment.google_event_id:
        return create_google_calendar_event(specialist, appointment)
    service = get_calendar_service(specialist)
    if not service:
        return False
    calendar_id = specialist.google_calendar_id or "primary"
    try:
        start_dt = appointment.appointment_date
        end_dt = start_dt + timedelta(minutes=appointment.duration or 60)
        timezone_str = "Europe/Moscow"
        event = {
            "summary": f"Консультация: {appointment.client_name}",
            "description": (
                f"Email: {appointment.client_email}\n"
                f"Телефон: {appointment.client_phone or '-'}\n"
                f"Telegram: {appointment.client_telegram or '-'}\n"
                f"{appointment.notes or ''}"
            ).strip(),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone_str},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone_str},
        }
        service.events().update(
            calendarId=calendar_id,
            eventId=appointment.google_event_id,
            body=event,
        ).execute()
        return True
    except Exception as e:
        logger.warning("Google Calendar: ошибка обновления события: %s", e)
    return False


def delete_google_calendar_event(specialist, appointment):
    """
    Удаляет событие из Google Calendar (при отмене записи).
    Если передан объект с атрибутом google_event_id, после удаления сбрасывает его и сохраняет (если у объекта есть save).
    """
    event_id = getattr(appointment, "google_event_id", None) or ""
    if not event_id:
        return True
    ok = _delete_event_by_id(specialist, event_id)
    if ok and hasattr(appointment, "save") and hasattr(appointment, "pk") and appointment.pk:
        appointment.google_event_id = ""
        appointment.save(update_fields=["google_event_id"])
    return ok


def _delete_event_by_id(specialist, event_id):
    """Удаляет событие в Google Calendar по event_id (без изменения модели)."""
    if not event_id:
        return True
    service = get_calendar_service(specialist)
    if not service:
        return False
    calendar_id = specialist.google_calendar_id or "primary"
    try:
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
        return True
    except Exception as e:
        logger.warning("Google Calendar: ошибка удаления события: %s", e)
    return False
