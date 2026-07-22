"""Admin A3b: week calendar view for platform bookings."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import Booking, Calendar
from app.services.bookings_hub import STATUS_LABELS
from app.services.platform_admin_domain import BOOKING_STATUSES

WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
GRID_START_HOUR = 8
GRID_END_HOUR = 21


def parse_week_start(raw: str | None) -> date:
    if raw:
        try:
            d = date.fromisoformat(raw.strip())
            return d - timedelta(days=d.weekday())
        except ValueError:
            pass
    today = date.today()
    return today - timedelta(days=today.weekday())


def week_range_label(week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    if week_start.month == week_end.month:
        return f"{week_start.day}-{week_end.day}.{week_start.month:02d}.{week_start.year}"
    return f"{week_start.day}.{week_start.month:02d} - {week_end.day}.{week_end.month:02d}.{week_end.year}"


def _grid_span_minutes() -> int:
    return (GRID_END_HOUR - GRID_START_HOUR) * 60


def _event_layout(booking_time: time, duration_min: int) -> tuple[float, float]:
    span = _grid_span_minutes()
    if span <= 0:
        return 0.0, 5.0
    start_min = booking_time.hour * 60 + booking_time.minute - GRID_START_HOUR * 60
    start_min = max(0, min(start_min, span))
    dur = max(duration_min or 60, 30)
    top_pct = start_min / span * 100
    height_pct = min(100 - top_pct, dur / span * 100)
    return round(top_pct, 2), round(max(height_pct, 4), 2)


def bookings_for_week(
    db: Session,
    week_start: date,
    *,
    consultant_id: int | None = None,
    calendar_id: int | None = None,
    status: str | None = None,
) -> list[Booking]:
    week_end = week_start + timedelta(days=6)
    query = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar).joinedload(Calendar.consultant),
        )
        .filter(Booking.booking_date >= week_start, Booking.booking_date <= week_end)
        .order_by(Booking.booking_date.asc(), Booking.booking_time.asc(), Booking.id.asc())
    )
    if calendar_id:
        query = query.filter(Booking.calendar_id == calendar_id)
    elif consultant_id:
        query = query.join(Calendar).filter(Calendar.consultant_id == consultant_id)
    if status and status in BOOKING_STATUSES:
        query = query.filter(Booking.status == status)
    return query.all()


def build_week_calendar(
    bookings: list[Booking],
    week_start: date,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    span = _grid_span_minutes()
    hours = list(range(GRID_START_HOUR, GRID_END_HOUR))
    days: list[dict[str, Any]] = []

    for i in range(7):
        d = week_start + timedelta(days=i)
        day_bookings = [b for b in bookings if b.booking_date == d]
        events = []
        for b in day_bookings:
            duration = b.service.duration_minutes if b.service else 60
            top_pct, height_pct = _event_layout(b.booking_time, duration)
            cal = b.calendar
            events.append(
                {
                    "id": b.id,
                    "client_name": b.client_name,
                    "time_label": b.booking_time.strftime("%H:%M"),
                    "time_hm": b.booking_time.strftime("%H:%M"),
                    "status": b.status,
                    "status_label": STATUS_LABELS.get(b.status, b.status),
                    "service_name": b.service.name if b.service else "-",
                    "calendar_name": cal.name if cal else "-",
                    "color": cal.color if cal else "#7d5cff",
                    "top_pct": top_pct,
                    "height_pct": height_pct,
                    "cancelled": b.status == "cancelled",
                }
            )
        days.append(
            {
                "date": d.isoformat(),
                "label": WEEKDAY_LABELS[i],
                "day_num": d.day,
                "is_today": d == today,
                "events": events,
            }
        )

    return {
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "week_label": week_range_label(week_start),
        "prev_week": (week_start - timedelta(days=7)).isoformat(),
        "next_week": (week_start + timedelta(days=7)).isoformat(),
        "grid_start_hour": GRID_START_HOUR,
        "grid_end_hour": GRID_END_HOUR,
        "hours": hours,
        "span_minutes": span,
        "days": days,
        "total_events": len(bookings),
    }
