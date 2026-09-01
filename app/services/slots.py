from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, Service, TimeSlot
from app.services.calendar_schedule import is_day_disabled


def _compute_available_slots(
    *,
    calendar: Calendar,
    service: Service,
    booking_date: date,
    time_slots: list[TimeSlot],
    existing_bookings: list[Booking],
    exclude_booking_id: int | None = None,
) -> dict:
    day_of_week = booking_date.weekday()
    if is_day_disabled(calendar, day_of_week):
        return {"available_slots": [], "available_windows": []}

    if exclude_booking_id:
        existing_bookings = [b for b in existing_bookings if b.id != exclude_booking_id]

    max_per_day = calendar.max_services_per_day or 0
    if max_per_day > 0 and len(existing_bookings) >= max_per_day:
        return {"available_slots": [], "available_windows": []}

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    tz = ZoneInfo(get_settings().timezone)
    now = datetime.now(tz)
    ahead = calendar.book_ahead_hours
    book_ahead_hours = 24 if ahead is None else int(ahead)
    min_start = now + timedelta(hours=book_ahead_hours)
    step_minutes = 15

    available_windows = []
    available_times = []

    for time_slot in time_slots:
        slot_start = datetime.combine(booking_date, time_slot.start_time, tzinfo=tz)
        slot_end = datetime.combine(booking_date, time_slot.end_time, tzinfo=tz)
        slot_duration = (slot_end - slot_start).total_seconds() / 60
        if service.duration_minutes > slot_duration:
            continue

        available_windows.append({
            "start_time": time_slot.start_time.strftime("%H:%M"),
            "end_time": time_slot.end_time.strftime("%H:%M"),
        })

        current_time = slot_start
        service_duration = timedelta(minutes=service.duration_minutes)
        while current_time + service_duration <= slot_end:
            if current_time < min_start:
                current_time += timedelta(minutes=step_minutes)
                continue

            overlaps = False
            for booking in existing_bookings:
                if not booking.booking_end_time:
                    continue
                booking_start = datetime.combine(booking_date, booking.booking_time, tzinfo=tz)
                booking_end = datetime.combine(booking_date, booking.booking_end_time, tzinfo=tz)
                if not (
                    current_time + service_duration + break_delta <= booking_start
                    or current_time >= booking_end + break_delta
                ):
                    overlaps = True
                    break

            if not overlaps:
                available_times.append({
                    "start_time": current_time.time().strftime("%H:%M"),
                    "end_time": (current_time + service_duration).time().strftime("%H:%M"),
                })
            current_time += timedelta(minutes=step_minutes)

    return {"available_slots": available_times, "available_windows": available_windows}


def get_available_slots(
    db: Session,
    calendar: Calendar,
    service: Service,
    booking_date: date,
    exclude_booking_id: int | None = None,
) -> dict:
    day_of_week = booking_date.weekday()
    if is_day_disabled(calendar, day_of_week):
        return {"available_slots": [], "available_windows": []}
    time_slots = (
        db.query(TimeSlot)
        .filter(
            TimeSlot.calendar_id == calendar.id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.is_available.is_(True),
        )
        .order_by(TimeSlot.start_time)
        .all()
    )
    existing_bookings = (
        db.query(Booking)
        .filter(
            Booking.calendar_id == calendar.id,
            Booking.booking_date == booking_date,
            Booking.status.in_(["pending", "confirmed"]),
        )
        .all()
    )
    return _compute_available_slots(
        calendar=calendar,
        service=service,
        booking_date=booking_date,
        time_slots=time_slots,
        existing_bookings=existing_bookings,
        exclude_booking_id=exclude_booking_id,
    )


async def get_available_slots_async(
    db: AsyncSession,
    calendar: Calendar,
    service: Service,
    booking_date: date,
    exclude_booking_id: int | None = None,
) -> dict:
    """Async hot-path for public / specialist slot JSON endpoints."""
    day_of_week = booking_date.weekday()
    if is_day_disabled(calendar, day_of_week):
        return {"available_slots": [], "available_windows": []}

    time_slots = list(
        (
            await db.execute(
                select(TimeSlot)
                .where(
                    TimeSlot.calendar_id == calendar.id,
                    TimeSlot.day_of_week == day_of_week,
                    TimeSlot.is_available.is_(True),
                )
                .order_by(TimeSlot.start_time)
            )
        ).scalars().all()
    )
    existing_bookings = list(
        (
            await db.execute(
                select(Booking).where(
                    Booking.calendar_id == calendar.id,
                    Booking.booking_date == booking_date,
                    Booking.status.in_(["pending", "confirmed"]),
                )
            )
        ).scalars().all()
    )
    return _compute_available_slots(
        calendar=calendar,
        service=service,
        booking_date=booking_date,
        time_slots=time_slots,
        existing_bookings=existing_bookings,
        exclude_booking_id=exclude_booking_id,
    )
