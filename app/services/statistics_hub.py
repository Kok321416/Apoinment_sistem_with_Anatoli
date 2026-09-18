"""Specialist statistics hub: status counts and consultation rows for a date range."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core import Booking, Calendar, CalendarBlock
from app.services.bookings_hub import STATUS_LABELS, serialize_booking

STATUS_ORDER = ("pending", "confirmed", "completed", "cancelled")
FILTERABLE_STATUSES = frozenset(STATUS_ORDER)


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


def parse_status_filters(raw_values: list[str] | None) -> list[str]:
    """Return selected statuses; empty list means all statuses."""
    if not raw_values:
        return []
    selected: list[str] = []
    for raw in raw_values:
        for part in str(raw or "").split(","):
            key = part.strip().lower()
            if key in FILTERABLE_STATUSES and key not in selected:
                selected.append(key)
    return selected


def status_filter_query(statuses: list[str]) -> str:
    return "&".join(f"status={s}" for s in statuses)


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
    statuses: list[str] | None = None,
) -> list[Booking]:
    if not cal_ids:
        return []
    clauses = [
        Booking.calendar_id.in_(cal_ids),
        Booking.booking_date >= date_from,
        Booking.booking_date <= date_to,
    ]
    if statuses:
        clauses.append(Booking.status.in_(statuses))
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.calendar))
        .where(*clauses)
        .order_by(Booking.booking_date, Booking.booking_time)
    )
    return list(result.scalars().unique().all())


async def blocks_in_range(
    db: AsyncSession,
    *,
    cal_ids: list[int],
    date_from: date,
    date_to: date,
    statuses: list[str] | None = None,
) -> list[CalendarBlock]:
    """Мероприятия for the same period.

    Mapping: pending/confirmed → active events; cancelled → cancelled events;
    completed-only → no events.
    """
    if not cal_ids:
        return []
    if statuses:
        block_statuses: list[str] = []
        if any(s in ("pending", "confirmed") for s in statuses):
            block_statuses.append("active")
        if "cancelled" in statuses:
            block_statuses.append("cancelled")
        if not block_statuses:
            return []
    else:
        block_statuses = ["active", "cancelled"]

    result = await db.execute(
        select(CalendarBlock)
        .options(selectinload(CalendarBlock.calendar))
        .where(
            CalendarBlock.calendar_id.in_(cal_ids),
            CalendarBlock.block_date >= date_from,
            CalendarBlock.block_date <= date_to,
            CalendarBlock.status.in_(block_statuses),
        )
        .order_by(CalendarBlock.block_date, CalendarBlock.start_time)
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
                "id": b.id,
                "kind": "booking",
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


def export_block_rows(blocks: list[CalendarBlock]) -> list[dict[str, Any]]:
    rows = []
    for block in blocks:
        start = block.start_time.strftime("%H:%M") if block.start_time else ""
        end = block.end_time.strftime("%H:%M") if block.end_time else ""
        time_range = f"{start}–{end}" if start and end else start
        status = block.status or "active"
        status_label = "Отменена" if status == "cancelled" else "Мероприятие"
        rows.append(
            {
                "id": block.id,
                "kind": "event",
                "date": block.block_date.isoformat() if block.block_date else "",
                "time": start,
                "time_range": time_range,
                "status": status,
                "status_label": status_label,
                "service": "Мероприятие",
                "calendar": block.calendar.name if block.calendar else "",
                "client_name": block.title or "Мероприятие",
                "client_phone": "",
                "client_email": "",
                "client_telegram": "",
                "notes": block.notes or "",
                "price": "",
            }
        )
    return rows


def merge_export_rows(
    booking_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(booking_rows) + list(event_rows)
    merged.sort(key=lambda r: (r.get("date") or "", r.get("time") or "", r.get("kind") or ""))
    return merged


async def build_statistics_payload(
    db: AsyncSession,
    *,
    consultant_id: int,
    date_from: date,
    date_to: date,
    today: date | None = None,
    now: time | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    now = now or datetime.now().time()
    statuses = list(statuses or [])
    cal_ids = await consultant_calendar_ids(db, consultant_id)
    counts = await status_counts_in_range(
        db, cal_ids=cal_ids, date_from=date_from, date_to=date_to
    )
    bookings = await bookings_in_range(
        db, cal_ids=cal_ids, date_from=date_from, date_to=date_to, statuses=statuses or None
    )
    blocks = await blocks_in_range(
        db, cal_ids=cal_ids, date_from=date_from, date_to=date_to, statuses=statuses or None
    )
    rows = merge_export_rows(export_rows(bookings, today, now), export_block_rows(blocks))
    return {
        "date_from": date_from,
        "date_to": date_to,
        "counts": counts,
        "cards": status_cards(counts),
        "bookings": bookings,
        "export_rows": rows,
        "booking_count": len(rows),
        "status_filters": statuses,
    }


async def delete_statistics_items_async(
    db: AsyncSession,
    *,
    consultant_id: int,
    booking_ids: list[int],
    event_ids: list[int],
) -> tuple[int, int]:
    """Hard-delete selected bookings and calendar blocks owned by consultant."""
    from app.models.diagnostics import DiagnosticAttempt

    cal_ids = await consultant_calendar_ids(db, consultant_id)
    if not cal_ids:
        return 0, 0

    deleted_bookings = 0
    if booking_ids:
        from sqlalchemy import update

        bookings = list(
            (
                await db.execute(
                    select(Booking).where(
                        Booking.id.in_(booking_ids),
                        Booking.calendar_id.in_(cal_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        ids = [b.id for b in bookings]
        if ids:
            await db.execute(
                update(DiagnosticAttempt)
                .where(DiagnosticAttempt.booking_id.in_(ids))
                .values(booking_id=None)
            )
            for b in bookings:
                await db.delete(b)
            deleted_bookings = len(bookings)

    deleted_events = 0
    if event_ids:
        blocks = list(
            (
                await db.execute(
                    select(CalendarBlock).where(
                        CalendarBlock.id.in_(event_ids),
                        CalendarBlock.calendar_id.in_(cal_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for block in blocks:
            await db.delete(block)
        deleted_events = len(blocks)

    if deleted_bookings or deleted_events:
        await db.commit()
    return deleted_bookings, deleted_events
