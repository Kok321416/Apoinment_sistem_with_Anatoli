"""Specialist statistics hub: status counts and consultation rows for a date range."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core import Booking, Calendar
from app.services.bookings_hub import STATUS_LABELS, serialize_booking

STATUS_ORDER = ("pending", "confirmed", "completed", "cancelled")


def default_date_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = today.replace(day=1)
    return start, today


def parse_range(date_from: str | None, date_to: str | None, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    default_from, default_to = default_date_range(today)

    def _parse(raw: str | None, fallback: date) -> date:
        if not raw:
            return fallback
        try:
            return date.fromisoformat(raw.strip()[:10])
        except ValueError:
            return fallback

    start = _parse(date_from, default_from)
    end = _parse(date_to, default_to)
    if end < start:
        start, end = end, start
    return start, end


async def consultant_calendar_ids(db: AsyncSession, consultant_id: int) -> list[int]:
    rows = (
        await db.execute(select(Calendar.id).where(Calendar.consultant_id == consultant_id))
    ).scalars().all()
    return [int(x) for x in rows]


async def bookings_in_range(
    db: AsyncSession,
    *,
    cal_ids: list[int],
    date_from: date,
    date_to: date,
) -> list[Booking]:
    if not cal_ids:
        return []
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.calendar))
        .where(
            Booking.calendar_id.in_(cal_ids),
            Booking.booking_date >= date_from,
            Booking.booking_date <= date_to,
        )
        .order_by(Booking.booking_date, Booking.booking_time)
    )
    return list(result.scalars().unique().all())


async def status_counts_in_range(
    db: AsyncSession,
    *,
    cal_ids: list[int],
    date_from: date,
    date_to: date,
) -> dict[str, int]:
    counts = {s: 0 for s in STATUS_ORDER}
    counts["total"] = 0
    if not cal_ids:
        return counts
    rows = (
        await db.execute(
            select(Booking.status, func.count(Booking.id))
            .where(
                Booking.calendar_id.in_(cal_ids),
                Booking.booking_date >= date_from,
                Booking.booking_date <= date_to,
            )
            .group_by(Booking.status)
        )
    ).all()
    for status, n in rows:
        key = str(status or "")
        if key in counts:
            counts[key] = int(n)
        counts["total"] += int(n)
    return counts


def status_cards(counts: dict[str, int]) -> list[dict[str, Any]]:
    labels = {
        "total": "Всего",
        "pending": "Ожидают",
        "confirmed": "Подтверждены",
        "completed": "Завершены",
        "cancelled": "Отменены",
    }
    order = ("total",) + STATUS_ORDER
    return [
        {
            "key": key,
            "label": labels[key],
            "value": int(counts.get(key, 0)),
            "status_label": STATUS_LABELS.get(key, labels[key]),
        }
        for key in order
    ]


def export_rows(bookings: list[Booking], today: date, now: time) -> list[dict[str, Any]]:
    rows = []
    for b in bookings:
        s = serialize_booking(b, today, now)
        rows.append(
            {
                "date": s["booking_date"],
                "time": s["booking_time"],
                "time_range": s["time_range"],
                "status": s["status"],
                "status_label": s["status_label"],
                "service": s["service_name"],
                "calendar": s["calendar_name"],
                "client_name": s["client_name"],
                "client_phone": s["client_phone"],
                "client_email": s["client_email"],
                "client_telegram": s["client_telegram"],
                "notes": s["notes"],
                "price": s["service_price"],
            }
        )
    return rows


async def build_statistics_payload(
    db: AsyncSession,
    *,
    consultant_id: int,
    date_from: date,
    date_to: date,
    today: date | None = None,
    now: time | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    now = now or datetime.now().time()
    cal_ids = await consultant_calendar_ids(db, consultant_id)
    counts = await status_counts_in_range(
        db, cal_ids=cal_ids, date_from=date_from, date_to=date_to
    )
    bookings = await bookings_in_range(
        db, cal_ids=cal_ids, date_from=date_from, date_to=date_to
    )
    return {
        "date_from": date_from,
        "date_to": date_to,
        "counts": counts,
        "cards": status_cards(counts),
        "bookings": bookings,
        "export_rows": export_rows(bookings, today, now),
        "booking_count": len(bookings),
    }
