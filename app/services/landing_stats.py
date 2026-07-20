from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, Consultant

# Shown when DB is empty so the landing never looks abandoned.
MIN_DISPLAY = {
    "bookings": 120,
    "specialists": 40,
    "calendars": 35,
}


def landing_stats(db: Session) -> dict[str, int]:
    bookings = db.query(func.count(Booking.id)).scalar() or 0
    specialists = db.query(func.count(Consultant.id)).scalar() or 0
    calendars = db.query(func.count(Calendar.id)).scalar() or 0
    return {
        "bookings": max(bookings, MIN_DISPLAY["bookings"]),
        "specialists": max(specialists, MIN_DISPLAY["specialists"]),
        "calendars": max(calendars, MIN_DISPLAY["calendars"]),
        "bookings_real": bookings,
        "specialists_real": specialists,
        "calendars_real": calendars,
    }
