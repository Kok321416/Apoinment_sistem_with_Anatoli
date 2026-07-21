"""Bookings hub: dashboard, grouping, sidebar, serialization."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.core import Booking

MONTH_NAMES = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "completed": "Завершена",
    "cancelled": "Отменена",
}


def _booking_price(booking: Booking) -> Decimal:
    if booking.service and booking.service.price is not None:
        return Decimal(booking.service.price)
    return Decimal(0)


def _format_time(t: time | None) -> str:
    if not t:
        return ""
    return t.strftime("%H:%M")


def _day_label(d: date, today: date) -> str:
    if d == today:
        return "Сегодня"
    if d == today + timedelta(days=1):
        return "Завтра"
    return f"{d.day} {MONTH_NAMES[d.month - 1]}"


def _is_past(booking: Booking, today: date, now: time) -> bool:
    if booking.booking_date < today:
        return True
    if booking.booking_date == today and booking.booking_time < now:
        return True
    return False


def serialize_booking(booking: Booking, today: date, now: time) -> dict:
    service = booking.service
    calendar = booking.calendar
    is_past = _is_past(booking, today, now)
    start = _format_time(booking.booking_time)
    end = _format_time(booking.booking_end_time)
    time_range = f"{start}–{end}" if end else start
    return {
        "id": booking.id,
        "client_name": booking.client_name,
        "client_phone": booking.client_phone or "",
        "client_email": booking.client_email or "",
        "client_telegram": booking.client_telegram or "",
        "service_name": service.name if service else "—",
        "service_duration": service.duration_minutes if service else None,
        "service_price": float(_booking_price(booking)) if _booking_price(booking) else None,
        "calendar_name": calendar.name if calendar else "—",
        "calendar_color": calendar.color if calendar else "#6C63FF",
        "calendar_id": calendar.id if calendar else None,
        "service_id": service.id if service else None,
        "status": booking.status,
        "status_label": STATUS_LABELS.get(booking.status, booking.status),
        "booking_date": booking.booking_date.isoformat(),
        "booking_time": start,
        "time_range": time_range,
        "day_label": _day_label(booking.booking_date, today),
        "is_past": is_past,
        "notes": booking.notes or "",
        "search_text": " ".join(filter(None, [
            booking.client_name,
            booking.client_phone,
            booking.client_email,
            service.name if service else "",
            calendar.name if calendar else "",
        ])).lower(),
    }


def group_by_day(bookings: list[Booking], today: date, now: time, *, reverse: bool = False) -> list[dict]:
    by_date: dict[date, list[Booking]] = {}
    for booking in bookings:
        by_date.setdefault(booking.booking_date, []).append(booking)

    dates = sorted(by_date.keys(), reverse=reverse)
    groups = []
    for d in dates:
        items = sorted(by_date[d], key=lambda b: b.booking_time)
        groups.append({
            "date": d.isoformat(),
            "label": _day_label(d, today),
            "bookings": [serialize_booking(b, today, now) for b in items],
        })
    return groups


def dashboard_stats(bookings: list[Booking], today: date) -> dict:
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=6)

    active = [b for b in bookings if b.status != "cancelled"]
    today_list = [b for b in active if b.booking_date == today]
    tomorrow_list = [b for b in active if b.booking_date == tomorrow]
    week_list = [b for b in active if today <= b.booking_date <= week_end]

    revenue_bookings = [b for b in active if b.status in ("pending", "confirmed", "completed")]
    week_revenue = sum(_booking_price(b) for b in revenue_bookings if today <= b.booking_date <= week_end)
    today_revenue = sum(_booking_price(b) for b in revenue_bookings if b.booking_date == today)

    return {
        "today_count": len(today_list),
        "tomorrow_count": len(tomorrow_list),
        "week_count": len(week_list),
        "week_revenue": float(week_revenue),
        "today_revenue": float(today_revenue),
    }


def sidebar_data(upcoming: list[Booking], today: date, now: time) -> dict:
    today_items = []
    for b in sorted(upcoming, key=lambda x: x.booking_time):
        if b.booking_date != today or b.status == "cancelled":
            continue
        today_items.append({
            "id": b.id,
            "time": _format_time(b.booking_time),
            "client_name": b.client_name,
            "status": b.status,
        })

    future = [
        b for b in upcoming
        if b.status in ("pending", "confirmed")
        and (b.booking_date > today or (b.booking_date == today and b.booking_time >= now))
    ]
    next_booking = None
    if future:
        nb = min(future, key=lambda b: (b.booking_date, b.booking_time))
        start_dt = datetime.combine(nb.booking_date, nb.booking_time)
        minutes_until = max(0, int((start_dt - datetime.now()).total_seconds() / 60))
        next_booking = {
            "id": nb.id,
            "client_name": nb.client_name,
            "time": _format_time(nb.booking_time),
            "day_label": _day_label(nb.booking_date, today),
            "minutes_until": minutes_until,
            "service_name": nb.service.name if nb.service else "—",
        }

    revenue_today = float(sum(
        _booking_price(b) for b in upcoming
        if b.booking_date == today and b.status in ("pending", "confirmed", "completed")
    ))

    return {
        "today_schedule": today_items,
        "next_booking": next_booking,
        "revenue_today": revenue_today,
        "free_time_note": "Скоро",
    }


def stats_bookings(db: Session, cal_ids: list[int]) -> list[Booking]:
    if not cal_ids:
        return []
    from sqlalchemy.orm import joinedload

    return (
        db.query(Booking)
        .options(joinedload(Booking.service), joinedload(Booking.calendar))
        .filter(
            Booking.calendar_id.in_(cal_ids),
            Booking.status.in_(["pending", "confirmed", "completed"]),
        )
        .all()
    )


def build_bookings_payload(
    db: Session,
    cal_ids: list[int],
    upcoming: list[Booking],
    past: list[Booking],
    today: date,
    now: time,
) -> dict:
    all_stats = stats_bookings(db, cal_ids)
    return {
        "dashboard": dashboard_stats(all_stats, today),
        "upcoming_groups": group_by_day(upcoming, today, now),
        "past_groups": group_by_day(past, today, now, reverse=True),
        "sidebar": sidebar_data(upcoming, today, now),
    }
