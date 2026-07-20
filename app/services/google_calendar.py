import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, Integration

logger = logging.getLogger(__name__)
settings = get_settings()
TIMEZONE_STR = "Europe/Moscow"


def _get_calendar_service(integration: Integration):
    if not integration or not (integration.google_refresh_token or "").strip():
        return None
    client_id = settings.google_oauth_client_id
    client_secret = settings.google_oauth_client_secret
    if not client_id or not client_secret:
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=integration.google_refresh_token.strip(),
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=settings.google_calendar_scopes,
        )
        creds.refresh(Request())
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.warning("Google Calendar service error: %s", e)
        return None


def _booking_start_end(booking: Booking):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.timezone)
    start_dt = datetime.combine(booking.booking_date, booking.booking_time, tzinfo=tz)
    if booking.booking_end_time:
        end_dt = datetime.combine(booking.booking_date, booking.booking_end_time, tzinfo=tz)
    else:
        duration = booking.service.duration_minutes if booking.service else 60
        end_dt = start_dt + timedelta(minutes=duration)
    return start_dt, end_dt


def create_booking_google_event(db: Session, integration: Integration, booking: Booking) -> bool:
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (integration.google_calendar_id or "").strip() or "primary"
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
        created = service.events().insert(calendarId=calendar_id, body=event).execute()
        event_id = created.get("id")
        if event_id:
            booking.google_event_id = event_id
            db.commit()
            return True
    except Exception as e:
        logger.warning("Google Calendar create error: %s", e)
    return False


def update_booking_google_event(db: Session, integration: Integration, booking: Booking) -> bool:
    if not booking.google_event_id:
        return create_booking_google_event(db, integration, booking)
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (integration.google_calendar_id or "").strip() or "primary"
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
        return True
    except Exception as e:
        logger.warning("Google Calendar update error: %s", e)
    return False


def delete_booking_google_event(integration: Integration, booking: Booking, clear_event_id: bool = True) -> bool:
    event_id = (booking.google_event_id or "").strip()
    if not event_id:
        return True
    service = _get_calendar_service(integration)
    if not service:
        return False
    calendar_id = (integration.google_calendar_id or "").strip() or "primary"
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        if clear_event_id:
            booking.google_event_id = None
        return True
    except Exception as e:
        logger.warning("Google Calendar delete error: %s", e)
    return False


def get_integration_for_booking(db: Session, booking: Booking) -> Integration | None:
    consultant = None
    if booking.calendar and booking.calendar.consultant:
        consultant = booking.calendar.consultant
    elif booking.service and booking.service.consultant:
        consultant = booking.service.consultant
    if not consultant:
        return None
    if consultant.integration:
        return consultant.integration
    integration = Integration(consultant_id=consultant.id)
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def sync_booking_to_google(db: Session, booking: Booking, created: bool = False) -> None:
    integration = get_integration_for_booking(db, booking)
    if not integration or not integration.google_calendar_connected:
        return
    if not (integration.google_refresh_token or "").strip():
        return
    if booking.status == "cancelled":
        if booking.google_event_id:
            delete_booking_google_event(integration, booking)
            db.commit()
        return
    if created:
        create_booking_google_event(db, integration, booking)
    else:
        update_booking_google_event(db, integration, booking)
