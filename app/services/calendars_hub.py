"""Calendars hub: dashboard stats, serialization, activity feed."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.core import Booking, Calendar, Service, TimeSlot


def _calendar_ids(calendars: list[Calendar]) -> list[int]:
    return [c.id for c in calendars]


def per_calendar_stats(db: Session, cal_ids: list[int]) -> dict[int, dict]:
    if not cal_ids:
        return {}

    stats = {
        cid: {
            "slots": 0,
            "services": 0,
            "today_bookings": 0,
            "last_booking": None,
            "total_bookings": 0,
        }
        for cid in cal_ids
    }

    for cid, cnt in (
        db.query(TimeSlot.calendar_id, func.count(TimeSlot.id))
        .filter(TimeSlot.calendar_id.in_(cal_ids))
        .group_by(TimeSlot.calendar_id)
        .all()
    ):
        stats[cid]["slots"] = cnt

    for cid, cnt in (
        db.query(Service.calendar_id, func.count(Service.id))
        .filter(Service.calendar_id.in_(cal_ids), Service.is_active.is_(True))
        .group_by(Service.calendar_id)
        .all()
    ):
        if cid:
            stats[cid]["services"] = cnt

    today = date.today()
    for cid, cnt in (
        db.query(Booking.calendar_id, func.count(Booking.id))
        .filter(Booking.calendar_id.in_(cal_ids), Booking.booking_date == today)
        .group_by(Booking.calendar_id)
        .all()
    ):
        stats[cid]["today_bookings"] = cnt

    for cid, cnt in (
        db.query(Booking.calendar_id, func.count(Booking.id))
        .filter(Booking.calendar_id.in_(cal_ids))
        .group_by(Booking.calendar_id)
        .all()
    ):
        stats[cid]["total_bookings"] = cnt

    for cid, last_date in (
        db.query(Booking.calendar_id, func.max(Booking.booking_date))
        .filter(Booking.calendar_id.in_(cal_ids))
        .group_by(Booking.calendar_id)
        .all()
    ):
        stats[cid]["last_booking"] = last_date

    return stats


def dashboard_stats(calendars: list[Calendar], stats_map: dict[int, dict]) -> dict:
    total = len(calendars)
    active = sum(1 for c in calendars if c.is_active)
    slots_total = sum(s.get("slots", 0) for s in stats_map.values())
    today_bookings = sum(s.get("today_bookings", 0) for s in stats_map.values())
    activity_pct = round(active / total * 100) if total else 0

    timestamps = [c.updated_at or c.created_at for c in calendars if c.updated_at or c.created_at]
    last_updated = max(timestamps) if timestamps else None

    return {
        "total": total,
        "active": active,
        "slots_total": slots_total,
        "today_bookings": today_bookings,
        "activity_pct": activity_pct,
        "last_updated": last_updated.isoformat() if last_updated else None,
    }


def _status_key(calendar: Calendar) -> str:
    return "active" if calendar.is_active else "inactive"


def _status_label(calendar: Calendar) -> str:
    return "Активен" if calendar.is_active else "Выключен"


def _is_archive(calendar: Calendar, stats: dict) -> bool:
    if calendar.is_active:
        return False
    if stats.get("total_bookings", 0) > 0:
        return False
    if stats.get("slots", 0) > 0:
        return False
    created = calendar.created_at
    if created and (datetime.utcnow() - created).days < 14:
        return False
    return True


def serialize_calendar(calendar: Calendar, booking_url: str, stats: dict) -> dict:
    reminders_on = (calendar.reminder_hours_first or 0) > 0 or (calendar.reminder_hours_second or 0) > 0
    last_booking = stats.get("last_booking")
    activity_score = stats.get("today_bookings", 0) * 10 + stats.get("total_bookings", 0)
    return {
        "id": calendar.id,
        "name": calendar.name,
        "color": calendar.color or "#7d5cff",
        "is_active": calendar.is_active,
        "status": _status_key(calendar),
        "status_label": _status_label(calendar),
        "is_archive": _is_archive(calendar, stats),
        "time_slots_count": stats.get("slots", 0),
        "services_count": stats.get("services", 0),
        "today_bookings": stats.get("today_bookings", 0),
        "total_bookings": stats.get("total_bookings", 0),
        "last_booking": last_booking.isoformat() if last_booking else None,
        "created_at": calendar.created_at.isoformat() if calendar.created_at else None,
        "updated_at": calendar.updated_at.isoformat() if calendar.updated_at else None,
        "break_minutes": calendar.break_between_services_minutes or 0,
        "max_per_day": calendar.max_services_per_day or 0,
        "reminders_enabled": reminders_on,
        "booking_url": booking_url,
        "manage_url": f"/calendars/{calendar.id}/",
        "settings_url": f"/calendars/{calendar.id}/settings/",
        "activity_score": activity_score,
    }


def recent_activity(calendars: list[Calendar], limit: int = 8) -> list[dict]:
    events: list[dict] = []
    for cal in calendars:
        if cal.created_at:
            events.append({
                "calendar_id": cal.id,
                "calendar_name": cal.name,
                "action": "created",
                "action_label": "Создан",
                "at": cal.created_at,
            })
        if cal.updated_at and cal.created_at and cal.updated_at > cal.created_at + timedelta(seconds=1):
            label = "Изменён"
            action = "updated"
            if not cal.is_active:
                label = "Выключен"
                action = "disabled"
            events.append({
                "calendar_id": cal.id,
                "calendar_name": cal.name,
                "action": action,
                "action_label": label,
                "at": cal.updated_at,
            })

    events.sort(key=lambda e: e["at"] or datetime.min, reverse=True)
    result = []
    for event in events[:limit]:
        ts = event["at"]
        result.append({
            "calendar_id": event["calendar_id"],
            "calendar_name": event["calendar_name"],
            "action": event["action"],
            "action_label": event["action_label"],
            "at": ts.isoformat() if ts else None,
        })
    return result


def build_calendars_payload(db: Session, calendars: list[Calendar], public_url: str) -> dict:
    cal_ids = _calendar_ids(calendars)
    stats_map = per_calendar_stats(db, cal_ids)
    serialized = [
        serialize_calendar(cal, f"{public_url}c/{cal.id}/", stats_map.get(cal.id, {}))
        for cal in calendars
    ]
    return {
        "dashboard": dashboard_stats(calendars, stats_map),
        "calendars": serialized,
        "activity": recent_activity(calendars),
        "public_url": public_url,
    }
