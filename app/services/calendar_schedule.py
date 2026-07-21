"""Calendar schedule helpers: serialization, validation, presets."""
from __future__ import annotations

from datetime import datetime, time
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Calendar, TimeSlot
from app.services.entity_delete import detach_bookings_from_slots

DAYS_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MINUTES_PER_DAY = 24 * 60
SNAP_MINUTES = 15


def parse_disabled_weekdays(raw: str | None) -> set[int]:
    if not raw:
        return set()
    result: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            day = int(part)
        except ValueError:
            continue
        if 0 <= day <= 6:
            result.add(day)
    return result


def format_disabled_weekdays(days: Iterable[int]) -> str:
    return ",".join(str(d) for d in sorted(set(days)))


def time_to_str(value: time) -> str:
    return value.strftime("%H:%M")


def parse_time_str(raw: str | None) -> time | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


def time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def minutes_to_time(minutes: int) -> time:
    minutes = max(0, min(MINUTES_PER_DAY - 1, minutes))
    return time(minutes // 60, minutes % 60)


def snap_minutes(minutes: int) -> int:
    return round(minutes / SNAP_MINUTES) * SNAP_MINUTES


def slot_position(start: time, end: time) -> tuple[float, float]:
    start_m = time_to_minutes(start)
    end_m = time_to_minutes(end)
    top = start_m / MINUTES_PER_DAY * 100
    height = max((end_m - start_m) / MINUTES_PER_DAY * 100, 0.5)
    return round(top, 4), round(height, 4)


def validate_slot_times(start: time, end: time) -> str | None:
    if start >= end:
        return "Время начала должно быть раньше окончания"
    if time_to_minutes(end) > MINUTES_PER_DAY:
        return "Время окончания не может быть позже 23:59"
    return None


def serialize_slot(slot: TimeSlot) -> dict:
    top, height = slot_position(slot.start_time, slot.end_time)
    return {
        "id": slot.id,
        "day_of_week": slot.day_of_week,
        "start": time_to_str(slot.start_time),
        "end": time_to_str(slot.end_time),
        "top": top,
        "height": height,
        "is_available": bool(slot.is_available),
    }


def serialize_calendar_settings(calendar: Calendar) -> dict:
    disabled = parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
    return {
        "id": calendar.id,
        "name": calendar.name,
        "is_active": bool(calendar.is_active),
        "color": calendar.color,
        "break_between_services_minutes": calendar.break_between_services_minutes or 0,
        "max_services_per_day": calendar.max_services_per_day or 0,
        "book_ahead_hours": calendar.book_ahead_hours or 24,
        "reminder_hours_first": calendar.reminder_hours_first or 0,
        "reminder_hours_second": calendar.reminder_hours_second or 0,
        "disabled_weekdays": sorted(disabled),
    }


def slots_by_day(db: Session, calendar_id: int) -> list[list[TimeSlot]]:
    slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.calendar_id == calendar_id)
        .order_by(TimeSlot.day_of_week, TimeSlot.start_time)
        .all()
    )
    grouped: list[list[TimeSlot]] = [[] for _ in range(7)]
    for slot in slots:
        if 0 <= slot.day_of_week <= 6:
            grouped[slot.day_of_week].append(slot)
    return grouped


def serialize_week(calendar: Calendar, grouped: list[list[TimeSlot]]) -> list[dict]:
    disabled = parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
    week: list[dict] = []
    for day in range(7):
        day_slots = grouped[day]
        visible_slots = [
            serialize_slot(slot)
            for slot in day_slots
            if slot.is_available and day not in disabled
        ]
        week.append({
            "day": day,
            "name": DAYS_NAMES[day],
            "short": DAYS_SHORT[day],
            "is_working": day not in disabled,
            "slots": visible_slots,
            "all_slots": [serialize_slot(slot) for slot in day_slots],
        })
    return week


def build_schedule_payload(calendar: Calendar, grouped: list[list[TimeSlot]]) -> dict:
    settings = serialize_calendar_settings(calendar)
    return {
        "calendar": settings,
        "settings": settings,
        "week": serialize_week(calendar, grouped),
        "days_names": DAYS_NAMES,
        "days_short": DAYS_SHORT,
    }


def build_day_payload(calendar: Calendar, grouped: list[list[TimeSlot]], weekday: int) -> dict:
    if weekday < 0 or weekday > 6:
        raise ValueError("invalid weekday")
    disabled = parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
    day_slots = grouped[weekday]
    return {
        "day": weekday,
        "name": DAYS_NAMES[weekday],
        "short": DAYS_SHORT[weekday],
        "is_working": weekday not in disabled,
        "slots": [serialize_slot(slot) for slot in day_slots if slot.is_available],
        "all_slots": [serialize_slot(slot) for slot in day_slots],
    }


def set_day_working(calendar: Calendar, weekday: int, is_working: bool) -> None:
    disabled = parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
    if is_working:
        disabled.discard(weekday)
    else:
        disabled.add(weekday)
    calendar.disabled_weekdays = format_disabled_weekdays(disabled)


def clear_day_slots(db: Session, calendar_id: int, weekday: int) -> int:
    slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.calendar_id == calendar_id, TimeSlot.day_of_week == weekday)
        .all()
    )
    if not slots:
        return 0
    detach_bookings_from_slots(db, [slot.id for slot in slots])
    for slot in slots:
        db.delete(slot)
    return len(slots)


def copy_day_slots(db: Session, calendar: Calendar, source_day: int, target_days: list[int], replace: bool = True) -> int:
    source_slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.calendar_id == calendar.id, TimeSlot.day_of_week == source_day)
        .order_by(TimeSlot.start_time)
        .all()
    )
    created = 0
    for target_day in target_days:
        if target_day < 0 or target_day > 6 or target_day == source_day:
            continue
        if replace:
            clear_day_slots(db, calendar.id, target_day)
        for slot in source_slots:
            db.add(TimeSlot(
                calendar_id=calendar.id,
                day_of_week=target_day,
                start_time=slot.start_time,
                end_time=slot.end_time,
                is_available=slot.is_available,
            ))
            created += 1
    return created


def preset_workweek(db: Session, calendar: Calendar, source_day: int) -> int:
    return copy_day_slots(db, calendar, source_day, list(range(5)), replace=True)


def preset_fulltime(db: Session, calendar: Calendar, days: list[int] | None = None) -> int:
    target_days = days if days is not None else list(range(7))
    start = time(0, 0)
    end = time(23, 59)
    created = 0
    for day in target_days:
        if day < 0 or day > 6:
            continue
        clear_day_slots(db, calendar.id, day)
        db.add(TimeSlot(
            calendar_id=calendar.id,
            day_of_week=day,
            start_time=start,
            end_time=end,
            is_available=True,
        ))
        created += 1
        disabled = parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
        disabled.discard(day)
        calendar.disabled_weekdays = format_disabled_weekdays(disabled)
    return created


def is_day_disabled(calendar: Calendar, weekday: int) -> bool:
    return weekday in parse_disabled_weekdays(getattr(calendar, "disabled_weekdays", None))
