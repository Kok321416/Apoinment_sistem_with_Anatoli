"""Services catalog: serialization, stats, templates."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, Service

SERVICE_TEMPLATES = [
    {
        "id": "consult",
        "name": "Консультация",
        "description": "Индивидуальная консультация специалиста",
        "duration_minutes": 60,
        "price": 2500,
        "color": "#42c96b",
        "icon": "consult",
    },
    {
        "id": "repeat",
        "name": "Повторный приём",
        "description": "Повторная встреча с клиентом",
        "duration_minutes": 45,
        "price": 1800,
        "color": "#f59e0b",
        "icon": "repeat",
    },
    {
        "id": "online",
        "name": "Онлайн-встреча",
        "description": "Консультация по видеосвязи",
        "duration_minutes": 60,
        "price": 2000,
        "color": "#7c5cff",
        "icon": "online",
    },
    {
        "id": "massage",
        "name": "Массаж",
        "description": "Расслабляющий массаж",
        "duration_minutes": 90,
        "price": 3500,
        "color": "#eab308",
        "icon": "massage",
    },
    {
        "id": "manicure",
        "name": "Маникюр",
        "description": "Классический маникюр",
        "duration_minutes": 75,
        "price": 2200,
        "color": "#ec4899",
        "icon": "manicure",
    },
    {
        "id": "diagnostic",
        "name": "Диагностика",
        "description": "Первичная диагностика",
        "duration_minutes": 30,
        "price": 1500,
        "color": "#3b82f6",
        "icon": "diagnostic",
    },
]

ICON_MAP = {
    "consult": "💼",
    "repeat": "🔄",
    "online": "💻",
    "massage": "💆",
    "manicure": "💅",
    "diagnostic": "🔍",
    "default": "✨",
}


def service_icon(service: Service) -> str:
    key = (service.icon or "default").strip()
    return ICON_MAP.get(key, ICON_MAP["default"])


def _price_value(price: Decimal | None) -> float | None:
    if price is None:
        return None
    return float(price)


def serialize_service(service: Service, booking_count: int = 0) -> dict:
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description or "",
        "duration_minutes": service.duration_minutes,
        "price": _price_value(service.price),
        "price_display": f"{_price_value(service.price):.0f} ₽" if service.price else "—",
        "calendar_id": service.calendar_id,
        "calendar_name": service.calendar.name if service.calendar else None,
        "color": service.color or "#7d5cff",
        "icon": service.icon or "default",
        "icon_display": service_icon(service),
        "is_active": bool(service.is_active),
        "sort_order": service.sort_order or 0,
        "created_at": service.created_at.isoformat() if service.created_at else None,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        "booking_count": booking_count,
    }


def booking_counts(db: Session, service_ids: list[int]) -> dict[int, int]:
    if not service_ids:
        return {}
    rows = (
        db.query(Booking.service_id, func.count(Booking.id))
        .filter(Booking.service_id.in_(service_ids))
        .group_by(Booking.service_id)
        .all()
    )
    return {service_id: count for service_id, count in rows}


def dashboard_stats(services: list[Service], calendars: list[Calendar]) -> dict:
    active = [s for s in services if s.is_active]
    durations = [s.duration_minutes for s in services if s.duration_minutes]
    avg_duration = round(sum(durations) / len(durations)) if durations else 0
    calendar_ids = {s.calendar_id for s in services if s.calendar_id}
    return {
        "total": len(services),
        "active": len(active),
        "avg_duration": avg_duration,
        "calendars_used": len(calendar_ids),
        "calendars_total": len(calendars),
    }


def analytics_panel(db: Session, services: list[Service], consultant_id: int) -> dict:
    service_ids = [s.id for s in services]
    total_bookings = 0
    popular_name = "—"
    popular_count = 0
    if service_ids:
        total_bookings = (
            db.query(func.count(Booking.id))
            .filter(Booking.service_id.in_(service_ids))
            .scalar()
        ) or 0
        popular = (
            db.query(Booking.service_id, func.count(Booking.id).label("cnt"))
            .filter(Booking.service_id.in_(service_ids))
            .group_by(Booking.service_id)
            .order_by(func.count(Booking.id).desc())
            .first()
        )
        if popular:
            popular_count = popular.cnt
            svc = next((s for s in services if s.id == popular.service_id), None)
            popular_name = svc.name if svc else "—"

    prices = [_price_value(s.price) for s in services if s.price is not None]
    avg_price = round(sum(prices) / len(prices)) if prices else 0
    durations = [s.duration_minutes for s in services if s.duration_minutes]
    avg_duration = round(sum(durations) / len(durations)) if durations else 0

    confirmed = 0
    if service_ids:
        confirmed = (
            db.query(func.count(Booking.id))
            .filter(
                Booking.service_id.in_(service_ids),
                Booking.status.in_(["pending", "confirmed", "completed"]),
            )
            .scalar()
        ) or 0
    fill_rate = min(100, round(confirmed / max(total_bookings, 1) * 85)) if total_bookings else 0

    last_updated = None
    if services:
        latest = max(services, key=lambda s: s.updated_at or s.created_at or datetime.min)
        ts = latest.updated_at or latest.created_at
        last_updated = ts.isoformat() if ts else None

    return {
        "total_bookings": total_bookings,
        "fill_rate": fill_rate,
        "avg_price": avg_price,
        "avg_duration": avg_duration,
        "popular_service": popular_name,
        "popular_count": popular_count,
        "last_updated": last_updated,
    }


def service_statistics(db: Session, service: Service) -> dict:
    bookings = (
        db.query(Booking)
        .filter(Booking.service_id == service.id)
        .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
        .all()
    )
    count = len(bookings)
    last_booking = None
    if bookings:
        b = bookings[0]
        last_booking = f"{b.booking_date.isoformat()} {b.booking_time.strftime('%H:%M')}"
    price = _price_value(service.price) or 0
    avg_revenue = round(price) if count else 0
    return {
        "booking_count": count,
        "last_booking": last_booking,
        "avg_revenue": avg_revenue,
        "updated_at": (service.updated_at or service.created_at).isoformat()
        if (service.updated_at or service.created_at)
        else None,
    }


def serialize_calendar_option(calendar: Calendar) -> dict:
    return {"id": calendar.id, "name": calendar.name, "color": calendar.color}


def build_catalog_payload(db: Session, consultant_id: int, *, use_cache: bool = True) -> dict:
    from app.services.response_cache import TTL_SEC, catalog_key
    from app.services.ttl_cache import CACHE

    def _build() -> dict:
        services = (
            db.query(Service)
            .filter(Service.consultant_id == consultant_id)
            .order_by(Service.sort_order, Service.name)
            .all()
        )
        calendars = (
            db.query(Calendar)
            .filter(Calendar.consultant_id == consultant_id)
            .order_by(Calendar.name)
            .all()
        )
        counts = booking_counts(db, [s.id for s in services])
        return {
            "services": [serialize_service(s, counts.get(s.id, 0)) for s in services],
            "calendars": [serialize_calendar_option(c) for c in calendars],
            "dashboard": dashboard_stats(services, calendars),
            "analytics": analytics_panel(db, services, consultant_id),
            "templates": SERVICE_TEMPLATES,
        }

    if not use_cache:
        return _build()
    return CACHE.get_or_set(catalog_key(consultant_id), _build, ttl=TTL_SEC)


def next_sort_order(db: Session, consultant_id: int) -> int:
    max_order = (
        db.query(func.max(Service.sort_order))
        .filter(Service.consultant_id == consultant_id)
        .scalar()
    )
    return (max_order or 0) + 1
