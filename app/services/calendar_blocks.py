"""Calendar blocks (мероприятия) — occupy time so nobody can book."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Calendar, CalendarBlock, Consultant


def intervals_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
    *,
    break_delta: timedelta,
) -> bool:
    """True if intervals conflict including break gap between them."""
    return not (end_a + break_delta <= start_b or start_a >= end_b + break_delta)


def serialize_block(block: CalendarBlock) -> dict:
    return {
        "id": block.id,
        "kind": "event",
        "title": block.title,
        "notes": block.notes or "",
        "date": block.block_date.isoformat(),
        "time": block.start_time.strftime("%H:%M"),
        "end_time": block.end_time.strftime("%H:%M"),
        "status": block.status,
        "calendar_id": block.calendar_id,
        "client_name": block.title,
        "client_phone": "",
        "client_email": "",
        "client_telegram": "",
        "service": "Мероприятие",
        "service_id": None,
    }


async def list_active_blocks_for_day(
    db: AsyncSession,
    calendar_id: int,
    block_date: date,
) -> list[CalendarBlock]:
    rows = (
        await db.execute(
            select(CalendarBlock).where(
                CalendarBlock.calendar_id == calendar_id,
                CalendarBlock.block_date == block_date,
                CalendarBlock.status == "active",
            )
        )
    ).scalars().all()
    return list(rows)


async def list_active_blocks_in_range(
    db: AsyncSession,
    calendar_ids: list[int],
    start_date: date,
    end_date: date,
) -> list[CalendarBlock]:
    if not calendar_ids:
        return []
    rows = (
        await db.execute(
            select(CalendarBlock)
            .where(
                CalendarBlock.calendar_id.in_(calendar_ids),
                CalendarBlock.block_date >= start_date,
                CalendarBlock.block_date <= end_date,
                CalendarBlock.status == "active",
            )
            .order_by(CalendarBlock.block_date, CalendarBlock.start_time)
        )
    ).scalars().all()
    return list(rows)


def _block_overlap_error(
    blocks: list[CalendarBlock],
    *,
    block_date: date,
    start_time: time,
    end_time: time,
    break_delta: timedelta,
) -> str | None:
    start_dt = datetime.combine(block_date, start_time)
    end_dt = datetime.combine(block_date, end_time)
    for block in blocks:
        o_start = datetime.combine(block_date, block.start_time)
        o_end = datetime.combine(block_date, block.end_time)
        if intervals_overlap(start_dt, end_dt, o_start, o_end, break_delta=break_delta):
            return "Это время уже занято мероприятием."
    return None


def blocks_overlap_sync(
    db,
    *,
    calendar: Calendar,
    day: date,
    start_time: time,
    end_time: time,
) -> str | None:
    break_delta = timedelta(minutes=calendar.break_between_services_minutes or 0)
    blocks = (
        db.query(CalendarBlock)
        .filter(
            CalendarBlock.calendar_id == calendar.id,
            CalendarBlock.block_date == day,
            CalendarBlock.status == "active",
        )
        .all()
    )
    return _block_overlap_error(
        blocks,
        block_date=day,
        start_time=start_time,
        end_time=end_time,
        break_delta=break_delta,
    )


async def blocks_overlap_async(
    db: AsyncSession,
    *,
    calendar: Calendar,
    day: date,
    start_time: time,
    end_time: time,
    lock: bool = False,
) -> str | None:
    break_delta = timedelta(minutes=calendar.break_between_services_minutes or 0)
    q = select(CalendarBlock).where(
        CalendarBlock.calendar_id == calendar.id,
        CalendarBlock.block_date == day,
        CalendarBlock.status == "active",
    )
    if lock:
        q = q.with_for_update()
    blocks = list((await db.execute(q)).scalars().all())
    return _block_overlap_error(
        blocks,
        block_date=day,
        start_time=start_time,
        end_time=end_time,
        break_delta=break_delta,
    )


async def conflict_with_bookings_or_blocks(
    db: AsyncSession,
    *,
    calendar: Calendar,
    block_date: date,
    start_time: time,
    end_time: time,
    exclude_block_id: int | None = None,
    exclude_booking_id: int | None = None,
    lock: bool = False,
) -> str | None:
    """Return error message if interval overlaps bookings or other active blocks."""
    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)
    start_dt = datetime.combine(block_date, start_time)
    end_dt = datetime.combine(block_date, end_time)

    booking_q = select(Booking).where(
        Booking.calendar_id == calendar.id,
        Booking.booking_date == block_date,
        Booking.status.in_(["pending", "confirmed"]),
    )
    if exclude_booking_id is not None:
        booking_q = booking_q.where(Booking.id != exclude_booking_id)
    if lock:
        booking_q = booking_q.with_for_update()
    bookings = list((await db.execute(booking_q)).scalars().all())
    for booking in bookings:
        if not booking.booking_end_time:
            continue
        b_start = datetime.combine(block_date, booking.booking_time)
        b_end = datetime.combine(block_date, booking.booking_end_time)
        if intervals_overlap(start_dt, end_dt, b_start, b_end, break_delta=break_delta):
            return "Это время уже занято или слишком близко к другой записи."

    block_q = select(CalendarBlock).where(
        CalendarBlock.calendar_id == calendar.id,
        CalendarBlock.block_date == block_date,
        CalendarBlock.status == "active",
    )
    if exclude_block_id is not None:
        block_q = block_q.where(CalendarBlock.id != exclude_block_id)
    if lock:
        block_q = block_q.with_for_update()
    blocks = list((await db.execute(block_q)).scalars().all())
    return _block_overlap_error(
        blocks,
        block_date=block_date,
        start_time=start_time,
        end_time=end_time,
        break_delta=break_delta,
    )


async def create_calendar_block_async(
    db: AsyncSession,
    consultant: Consultant,
    *,
    calendar_id: int,
    title: str,
    block_date: date,
    start_time_str: str,
    end_time_str: str,
    notes: str = "",
    created_by_user_id: int | None = None,
) -> tuple[CalendarBlock | None, str | None]:
    from app.db_schema import ensure_calendar_blocks_schema

    ensure_calendar_blocks_schema()

    title = (title or "").strip()
    if not title:
        return None, "Укажите название мероприятия"
    if len(title) > 255:
        return None, "Слишком длинное название"

    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        return None, "Календарь не найден"
    if not calendar.is_active:
        return None, "Календарь отключён"

    try:
        start_time = datetime.strptime(start_time_str.strip(), "%H:%M").time()
        end_time = datetime.strptime(end_time_str.strip(), "%H:%M").time()
    except ValueError:
        return None, "Некорректный формат времени"

    if end_time <= start_time:
        return None, "Время окончания должно быть позже начала"

    (
        await db.execute(select(Calendar).where(Calendar.id == calendar.id).with_for_update())
    ).scalar_one()

    err = await conflict_with_bookings_or_blocks(
        db,
        calendar=calendar,
        block_date=block_date,
        start_time=start_time,
        end_time=end_time,
        lock=True,
    )
    if err:
        return None, err

    block = CalendarBlock(
        calendar_id=calendar.id,
        title=title,
        notes=(notes or "").strip() or None,
        block_date=block_date,
        start_time=start_time,
        end_time=end_time,
        status="active",
        created_by_user_id=created_by_user_id,
    )
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block, None


async def cancel_calendar_block_async(
    db: AsyncSession,
    consultant: Consultant,
    block_id: int,
) -> tuple[CalendarBlock | None, str | None]:
    block = (
        await db.execute(
            select(CalendarBlock)
            .join(Calendar, CalendarBlock.calendar_id == Calendar.id)
            .where(
                CalendarBlock.id == block_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not block:
        return None, "Мероприятие не найдено"
    if block.status == "cancelled":
        return block, None
    block.status = "cancelled"
    await db.commit()
    await db.refresh(block)
    return block, None
