"""Admin A3: specialists, clients, bookings, calendars, security."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import AdminAuditLog, Booking, Calendar, ClientCard, Consultant, User
from app.services.bookings_hub import STATUS_LABELS

BOOKING_STATUSES = tuple(STATUS_LABELS.keys())


def _like(q: str) -> str:
    return f"%{q.strip()}%"


def search_specialists(db: Session, q: str, *, limit: int = 50) -> list[dict[str, Any]]:
    query = db.query(Consultant).options(joinedload(Consultant.user))
    q = (q or "").strip()
    if q:
        like = _like(q)
        filters = [
            Consultant.first_name.ilike(like),
            Consultant.last_name.ilike(like),
            Consultant.email.ilike(like),
            Consultant.phone.ilike(like),
        ]
        if q.isdigit():
            filters.append(Consultant.id == int(q))
        query = query.filter(or_(*filters))
    consultants = query.order_by(Consultant.id.desc()).limit(limit).all()
    if not consultants:
        return []
    ids = [c.id for c in consultants]
    stats = _specialist_stats_map(db, ids)
    return [
        {
            "consultant": c,
            "stats": stats.get(c.id, _empty_specialist_stats()),
        }
        for c in consultants
    ]


def _empty_specialist_stats() -> dict[str, int | float]:
    return {
        "clients_count": 0,
        "bookings_total": 0,
        "bookings_cancelled": 0,
        "cancel_rate_pct": 0.0,
    }


def _specialist_stats_map(db: Session, consultant_ids: list[int]) -> dict[int, dict[str, int | float]]:
    if not consultant_ids:
        return {}
    clients_rows = (
        db.query(ClientCard.consultant_id, func.count(ClientCard.id))
        .filter(ClientCard.consultant_id.in_(consultant_ids))
        .group_by(ClientCard.consultant_id)
        .all()
    )
    clients_map = {int(r[0]): int(r[1]) for r in clients_rows}
    booking_rows = (
        db.query(
            Calendar.consultant_id,
            func.count(Booking.id),
            func.sum(case((Booking.status == "cancelled", 1), else_=0)),
        )
        .join(Booking, Booking.calendar_id == Calendar.id)
        .filter(Calendar.consultant_id.in_(consultant_ids))
        .group_by(Calendar.consultant_id)
        .all()
    )
    out: dict[int, dict[str, int | float]] = {}
    for cid in consultant_ids:
        out[cid] = _empty_specialist_stats()
        out[cid]["clients_count"] = clients_map.get(cid, 0)
    for consultant_id, total, cancelled in booking_rows:
        cid = int(consultant_id)
        total_i = int(total or 0)
        cancelled_i = int(cancelled or 0)
        out.setdefault(cid, _empty_specialist_stats())
        out[cid]["bookings_total"] = total_i
        out[cid]["bookings_cancelled"] = cancelled_i
        out[cid]["cancel_rate_pct"] = round((cancelled_i / total_i * 100) if total_i else 0.0, 1)
    return out


def specialist_admin_card(db: Session, consultant_id: int) -> dict[str, Any] | None:
    consultant = (
        db.query(Consultant)
        .options(joinedload(Consultant.user), joinedload(Consultant.calendars))
        .filter(Consultant.id == consultant_id)
        .first()
    )
    if not consultant:
        return None
    stats = _specialist_stats_map(db, [consultant.id]).get(consultant.id, _empty_specialist_stats())
    from app.services.public_client import ensure_public_slug

    slug = ensure_public_slug(db, consultant)
    return {"consultant": consultant, "stats": stats, "public_slug": slug}


def search_platform_clients(db: Session, q: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Aggregate platform clients by client_user_id; orphan cards listed separately."""
    q = (q or "").strip()
    rows: list[dict[str, Any]] = []
    seen_user_ids: set[int] = set()

    user_query = (
        db.query(User)
        .join(Booking, Booking.client_user_id == User.id)
        .options(joinedload(User.social_accounts))
        .distinct()
    )
    if q:
        like = _like(q)
        filters = [
            User.email.ilike(like),
            User.username.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ]
        if q.isdigit():
            filters.append(User.id == int(q))
        user_query = user_query.filter(or_(*filters))
    for user in user_query.order_by(User.id.desc()).limit(limit).all():
        seen_user_ids.add(user.id)
        cards_count = (
            db.query(func.count(ClientCard.id))
            .filter(ClientCard.client_user_id == user.id)
            .scalar()
            or 0
        )
        bookings_count = (
            db.query(func.count(Booking.id)).filter(Booking.client_user_id == user.id).scalar() or 0
        )
        rows.append(
            {
                "key": f"user-{user.id}",
                "client_user_id": user.id,
                "name": f"{user.first_name} {user.last_name}".strip() or user.email or user.username,
                "email": user.email,
                "phone": None,
                "cards_count": int(cards_count),
                "bookings_count": int(bookings_count),
                "user": user,
            }
        )

    card_query = db.query(ClientCard).options(joinedload(ClientCard.consultant))
    if q:
        like = _like(q)
        filters = [
            ClientCard.name.ilike(like),
            ClientCard.email.ilike(like),
            ClientCard.phone.ilike(like),
            ClientCard.telegram.ilike(like),
        ]
        if q.isdigit():
            filters.append(ClientCard.id == int(q))
        card_query = card_query.filter(or_(*filters))
    for card in card_query.order_by(ClientCard.id.desc()).limit(limit * 2).all():
        if card.client_user_id and card.client_user_id in seen_user_ids:
            continue
        if card.client_user_id:
            user = db.get(User, card.client_user_id)
            bookings_count = (
                db.query(func.count(Booking.id))
                .filter(Booking.client_user_id == card.client_user_id)
                .scalar()
                or 0
            )
            rows.append(
                {
                    "key": f"user-{card.client_user_id}",
                    "client_user_id": card.client_user_id,
                    "name": card.name or (user and (user.email or user.username)) or "-",
                    "email": card.email or (user.email if user else None),
                    "phone": card.phone,
                    "cards_count": (
                        db.query(func.count(ClientCard.id))
                        .filter(ClientCard.client_user_id == card.client_user_id)
                        .scalar()
                        or 1
                    ),
                    "bookings_count": int(bookings_count),
                    "user": user,
                }
            )
            seen_user_ids.add(card.client_user_id)
        else:
            bookings_count = (
                db.query(func.count(Booking.id))
                .filter(Booking.client_card_id == card.id)
                .scalar()
                or 0
            )
            rows.append(
                {
                    "key": f"card-{card.id}",
                    "client_user_id": None,
                    "client_card_id": card.id,
                    "name": card.name or card.phone or card.email or f"Карточка #{card.id}",
                    "email": card.email,
                    "phone": card.phone,
                    "cards_count": 1,
                    "bookings_count": int(bookings_count),
                    "user": None,
                    "consultant": card.consultant,
                }
            )
        if len(rows) >= limit:
            break
    return rows[:limit]


def platform_client_detail(db: Session, *, user_id: int | None = None, card_id: int | None = None) -> dict[str, Any] | None:
    if user_id:
        user = db.get(User, user_id)
        if not user:
            return None
        cards = db.query(ClientCard).filter(ClientCard.client_user_id == user_id).all()
        bookings = (
            db.query(Booking)
            .options(joinedload(Booking.service), joinedload(Booking.calendar))
            .filter(Booking.client_user_id == user_id)
            .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
            .limit(30)
            .all()
        )
        return {"user": user, "cards": cards, "bookings": bookings}
    if card_id:
        card = (
            db.query(ClientCard)
            .options(joinedload(ClientCard.consultant))
            .filter(ClientCard.id == card_id)
            .first()
        )
        if not card:
            return None
        bookings = (
            db.query(Booking)
            .options(joinedload(Booking.service), joinedload(Booking.calendar))
            .filter(Booking.client_card_id == card.id)
            .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
            .limit(30)
            .all()
        )
        return {"card": card, "cards": [card], "bookings": bookings, "user": None}
    return None


def list_bookings(
    db: Session,
    *,
    status: str | None = None,
    consultant_id: int | None = None,
    q: str = "",
    limit: int = 50,
) -> list[Booking]:
    query = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar).joinedload(Calendar.consultant),
            joinedload(Booking.client_user),
        )
        .order_by(Booking.booking_date.desc(), Booking.booking_time.desc(), Booking.id.desc())
    )
    if status and status in BOOKING_STATUSES:
        query = query.filter(Booking.status == status)
    if consultant_id:
        query = query.join(Calendar).filter(Calendar.consultant_id == consultant_id)
    q = (q or "").strip()
    if q:
        like = _like(q)
        filters = [
            Booking.client_name.ilike(like),
            Booking.client_phone.ilike(like),
            Booking.client_email.ilike(like),
        ]
        if q.isdigit():
            filters.append(Booking.id == int(q))
        query = query.filter(or_(*filters))
    return query.limit(limit).all()


def admin_set_booking_status(
    db: Session, booking_id: int, new_status: str, *, notify: bool = True
) -> tuple[Booking | None, str | None]:
    if new_status not in BOOKING_STATUSES:
        return None, "Неизвестный статус"
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar).joinedload(Calendar.consultant),
        )
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        return None, "Запись не найдена"
    old_status = booking.status
    if old_status == new_status:
        return booking, None
    booking.status = new_status
    db.commit()
    if notify:
        from app.services.telegram import notify_booking_status_changed

        notify_booking_status_changed(db, booking, old_status)
    return booking, None


def admin_reschedule_booking(
    db: Session,
    booking_id: int,
    new_date,
    new_time_str: str,
) -> tuple[Booking | None, str | None]:
    from app.services.bookings import reschedule_booking

    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar).joinedload(Calendar.consultant),
        )
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        return None, "Запись не найдена"
    if isinstance(new_date, str):
        try:
            new_date = date.fromisoformat(new_date)
        except ValueError:
            return None, "Некорректная дата"
    err = reschedule_booking(db, booking, new_date, new_time_str)
    if err:
        return None, err
    db.refresh(booking)
    return booking, None


def list_calendars(
    db: Session,
    *,
    consultant_id: int | None = None,
    active_only: bool | None = None,
    q: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    from app.services.public_client import ensure_public_slug

    query = (
        db.query(Calendar)
        .options(joinedload(Calendar.consultant))
        .order_by(Calendar.id.desc())
    )
    if consultant_id:
        query = query.filter(Calendar.consultant_id == consultant_id)
    if active_only is True:
        query = query.filter(Calendar.is_active.is_(True))
    elif active_only is False:
        query = query.filter(Calendar.is_active.is_(False))
    q = (q or "").strip()
    if q:
        like = _like(q)
        filters = [Calendar.name.ilike(like)]
        if q.isdigit():
            filters.append(Calendar.id == int(q))
        query = query.filter(or_(*filters))
    calendars = query.limit(limit).all()
    rows = []
    for cal in calendars:
        slug = ensure_public_slug(db, cal.consultant) if cal.consultant else f"id-{cal.consultant_id}"
        bookings_count = (
            db.query(func.count(Booking.id)).filter(Booking.calendar_id == cal.id).scalar() or 0
        )
        rows.append(
            {
                "calendar": cal,
                "consultant": cal.consultant,
                "public_slug": slug,
                "bookings_count": int(bookings_count),
            }
        )
    return rows


def set_calendar_active(db: Session, calendar_id: int, *, is_active: bool) -> Calendar | None:
    cal = db.get(Calendar, calendar_id)
    if not cal:
        return None
    cal.is_active = is_active
    db.commit()
    return cal


def list_failed_logins(db: Session, *, limit: int = 50) -> list[AdminAuditLog]:
    return (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.action == "login_failed")
        .order_by(AdminAuditLog.id.desc())
        .limit(limit)
        .all()
    )


def list_security_events(db: Session, *, limit: int = 30) -> list[AdminAuditLog]:
    security_actions = (
        "login_failed",
        "impersonate_start",
        "impersonate_stop",
        "user_block",
        "user_unblock",
    )
    return (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.action.in_(security_actions))
        .order_by(AdminAuditLog.id.desc())
        .limit(limit)
        .all()
    )


def booking_admin_card(db: Session, booking_id: int) -> dict[str, Any] | None:
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.calendar).joinedload(Calendar.consultant),
            joinedload(Booking.client_user),
            joinedload(Booking.client_card),
        )
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        return None
    return {
        "booking": booking,
        "status_labels": STATUS_LABELS,
    }

async def _specialist_stats_map_async(db, consultant_ids: list[int]) -> dict[int, dict[str, int | float]]:
    from sqlalchemy import case, func, select

    if not consultant_ids:
        return {}
    clients_rows = await db.execute(
        select(ClientCard.consultant_id, func.count(ClientCard.id))
        .where(ClientCard.consultant_id.in_(consultant_ids))
        .group_by(ClientCard.consultant_id)
    )
    clients_map = {int(r[0]): int(r[1]) for r in clients_rows.all()}
    booking_rows = await db.execute(
        select(
            Calendar.consultant_id,
            func.count(Booking.id),
            func.sum(case((Booking.status == "cancelled", 1), else_=0)),
        )
        .join(Booking, Booking.calendar_id == Calendar.id)
        .where(Calendar.consultant_id.in_(consultant_ids))
        .group_by(Calendar.consultant_id)
    )
    out: dict[int, dict[str, int | float]] = {}
    for cid in consultant_ids:
        out[cid] = _empty_specialist_stats()
        out[cid]["clients_count"] = clients_map.get(cid, 0)
    for consultant_id, total, cancelled in booking_rows.all():
        cid = int(consultant_id)
        total_i = int(total or 0)
        cancelled_i = int(cancelled or 0)
        out.setdefault(cid, _empty_specialist_stats())
        out[cid]["bookings_total"] = total_i
        out[cid]["bookings_cancelled"] = cancelled_i
        out[cid]["cancel_rate_pct"] = round((cancelled_i / total_i * 100) if total_i else 0.0, 1)
    return out


async def search_specialists_async(db, q: str, *, limit: int = 50) -> list[dict[str, Any]]:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    q = (q or "").strip()
    stmt = select(Consultant).options(selectinload(Consultant.user))
    if q:
        like = _like(q)
        filters = [
            Consultant.first_name.ilike(like),
            Consultant.last_name.ilike(like),
            Consultant.email.ilike(like),
            Consultant.phone.ilike(like),
        ]
        if q.isdigit():
            filters.append(Consultant.id == int(q))
        stmt = stmt.where(or_(*filters))
    consultants = list((await db.execute(stmt.order_by(Consultant.id.desc()).limit(limit))).scalars().unique().all())
    if not consultants:
        return []
    ids = [c.id for c in consultants]
    stats = await _specialist_stats_map_async(db, ids)
    return [{"consultant": c, "stats": stats.get(c.id, _empty_specialist_stats())} for c in consultants]


async def specialist_admin_card_async(db, consultant_id: int) -> dict[str, Any] | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    consultant = (
        await db.execute(
            select(Consultant)
            .options(selectinload(Consultant.user), selectinload(Consultant.calendars))
            .where(Consultant.id == consultant_id)
        )
    ).scalar_one_or_none()
    if not consultant:
        return None
    stats = (await _specialist_stats_map_async(db, [consultant.id])).get(consultant.id, _empty_specialist_stats())
    from app.services.public_client import ensure_public_slug_async

    slug = await ensure_public_slug_async(db, consultant)
    return {"consultant": consultant, "stats": stats, "public_slug": slug}


async def search_platform_clients_async(db, q: str, *, limit: int = 50) -> list[dict[str, Any]]:
    from sqlalchemy import func, or_, select
    from sqlalchemy.orm import selectinload

    q = (q or "").strip()
    rows: list[dict[str, Any]] = []
    seen_user_ids: set[int] = set()
    user_stmt = (
        select(User)
        .join(Booking, Booking.client_user_id == User.id)
        .options(selectinload(User.social_accounts))
        .distinct()
    )
    if q:
        like = _like(q)
        filters = [
            User.email.ilike(like),
            User.username.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ]
        if q.isdigit():
            filters.append(User.id == int(q))
        user_stmt = user_stmt.where(or_(*filters))
    users = list((await db.execute(user_stmt.order_by(User.id.desc()).limit(limit))).scalars().unique().all())
    for user in users:
        seen_user_ids.add(user.id)
        cards_count = (
            await db.execute(select(func.count(ClientCard.id)).where(ClientCard.client_user_id == user.id))
        ).scalar() or 0
        bookings_count = (
            await db.execute(select(func.count(Booking.id)).where(Booking.client_user_id == user.id))
        ).scalar() or 0
        rows.append(
            {
                "key": f"user-{user.id}",
                "client_user_id": user.id,
                "name": f"{user.first_name} {user.last_name}".strip() or user.email or user.username,
                "email": user.email,
                "phone": None,
                "cards_count": int(cards_count),
                "bookings_count": int(bookings_count),
                "user": user,
            }
        )
    card_stmt = select(ClientCard).options(selectinload(ClientCard.consultant))
    if q:
        like = _like(q)
        filters = [
            ClientCard.name.ilike(like),
            ClientCard.email.ilike(like),
            ClientCard.phone.ilike(like),
            ClientCard.telegram.ilike(like),
        ]
        if q.isdigit():
            filters.append(ClientCard.id == int(q))
        card_stmt = card_stmt.where(or_(*filters))
    cards = list((await db.execute(card_stmt.order_by(ClientCard.id.desc()).limit(limit * 2))).scalars().unique().all())
    for card in cards:
        if card.client_user_id and card.client_user_id in seen_user_ids:
            continue
        if card.client_user_id:
            user = await db.get(User, card.client_user_id)
            bookings_count = (
                await db.execute(select(func.count(Booking.id)).where(Booking.client_user_id == card.client_user_id))
            ).scalar() or 0
            cards_n = (
                await db.execute(
                    select(func.count(ClientCard.id)).where(ClientCard.client_user_id == card.client_user_id)
                )
            ).scalar() or 1
            rows.append(
                {
                    "key": f"user-{card.client_user_id}",
                    "client_user_id": card.client_user_id,
                    "name": card.name or (user and (user.email or user.username)) or "-",
                    "email": card.email or (user.email if user else None),
                    "phone": card.phone,
                    "cards_count": int(cards_n),
                    "bookings_count": int(bookings_count),
                    "user": user,
                }
            )
            seen_user_ids.add(card.client_user_id)
        else:
            bookings_count = (
                await db.execute(select(func.count(Booking.id)).where(Booking.client_card_id == card.id))
            ).scalar() or 0
            rows.append(
                {
                    "key": f"card-{card.id}",
                    "client_user_id": None,
                    "client_card_id": card.id,
                    "name": card.name or card.phone or card.email or f"Карточка #{card.id}",
                    "email": card.email,
                    "phone": card.phone,
                    "cards_count": 1,
                    "bookings_count": int(bookings_count),
                    "user": None,
                    "consultant": card.consultant,
                }
            )
        if len(rows) >= limit:
            break
    return rows[:limit]


async def platform_client_detail_async(
    db, *, user_id: int | None = None, card_id: int | None = None
) -> dict[str, Any] | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    if user_id:
        user = await db.get(User, user_id)
        if not user:
            return None
        cards = list((await db.execute(select(ClientCard).where(ClientCard.client_user_id == user_id))).scalars().all())
        bookings = list(
            (
                await db.execute(
                    select(Booking)
                    .options(selectinload(Booking.service), selectinload(Booking.calendar))
                    .where(Booking.client_user_id == user_id)
                    .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
                    .limit(30)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return {"user": user, "cards": cards, "bookings": bookings}
    if card_id:
        card = (
            await db.execute(
                select(ClientCard).options(selectinload(ClientCard.consultant)).where(ClientCard.id == card_id)
            )
        ).scalar_one_or_none()
        if not card:
            return None
        bookings = list(
            (
                await db.execute(
                    select(Booking)
                    .options(selectinload(Booking.service), selectinload(Booking.calendar))
                    .where(Booking.client_card_id == card.id)
                    .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
                    .limit(30)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return {"card": card, "cards": [card], "bookings": bookings, "user": None}
    return None


async def list_bookings_async(
    db,
    *,
    status: str | None = None,
    consultant_id: int | None = None,
    q: str = "",
    limit: int = 50,
) -> list[Booking]:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Booking)
        .options(
            selectinload(Booking.service),
            selectinload(Booking.calendar).selectinload(Calendar.consultant),
            selectinload(Booking.client_user),
        )
        .order_by(Booking.booking_date.desc(), Booking.booking_time.desc(), Booking.id.desc())
    )
    if status and status in BOOKING_STATUSES:
        stmt = stmt.where(Booking.status == status)
    if consultant_id:
        stmt = stmt.join(Calendar).where(Calendar.consultant_id == consultant_id)
    q = (q or "").strip()
    if q:
        like = _like(q)
        filters = [
            Booking.client_name.ilike(like),
            Booking.client_phone.ilike(like),
            Booking.client_email.ilike(like),
        ]
        if q.isdigit():
            filters.append(Booking.id == int(q))
        stmt = stmt.where(or_(*filters))
    return list((await db.execute(stmt.limit(limit))).scalars().unique().all())


async def admin_set_booking_status_async(
    db, booking_id: int, new_status: str, *, notify: bool = True
) -> tuple[Booking | None, str | None]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    if new_status not in BOOKING_STATUSES:
        return None, "Неизвестный статус"
    booking = (
        await db.execute(
            select(Booking)
            .options(
                selectinload(Booking.service),
                selectinload(Booking.calendar).selectinload(Calendar.consultant),
            )
            .where(Booking.id == booking_id)
        )
    ).scalar_one_or_none()
    if not booking:
        return None, "Запись не найдена"
    old_status = booking.status
    if old_status == new_status:
        return booking, None
    booking.status = new_status
    await db.commit()
    if notify:
        from app.services.notify_bridge import schedule_status_changed

        schedule_status_changed(booking_id, old_status)
    return booking, None


async def admin_reschedule_booking_async(
    db,
    booking_id: int,
    new_date,
    new_time_str: str,
) -> tuple[Booking | None, str | None]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.services.bookings import reschedule_booking_async

    booking = (
        await db.execute(
            select(Booking)
            .options(
                selectinload(Booking.service),
                selectinload(Booking.calendar).selectinload(Calendar.consultant),
            )
            .where(Booking.id == booking_id)
        )
    ).scalar_one_or_none()
    if not booking:
        return None, "Запись не найдена"
    if isinstance(new_date, str):
        try:
            new_date = date.fromisoformat(new_date)
        except ValueError:
            return None, "Некорректная дата"
    err = await reschedule_booking_async(db, booking, new_date, new_time_str)
    if err:
        return None, err
    await db.refresh(booking)
    return booking, None


async def list_calendars_async(
    db,
    *,
    consultant_id: int | None = None,
    active_only: bool | None = None,
    q: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    from sqlalchemy import func, or_, select
    from sqlalchemy.orm import selectinload
    from app.services.public_client import ensure_public_slug_async

    stmt = select(Calendar).options(selectinload(Calendar.consultant)).order_by(Calendar.id.desc())
    if consultant_id:
        stmt = stmt.where(Calendar.consultant_id == consultant_id)
    if active_only is True:
        stmt = stmt.where(Calendar.is_active.is_(True))
    elif active_only is False:
        stmt = stmt.where(Calendar.is_active.is_(False))
    q = (q or "").strip()
    if q:
        like = _like(q)
        filters = [Calendar.name.ilike(like)]
        if q.isdigit():
            filters.append(Calendar.id == int(q))
        stmt = stmt.where(or_(*filters))
    calendars = list((await db.execute(stmt.limit(limit))).scalars().unique().all())
    rows = []
    for cal in calendars:
        slug = await ensure_public_slug_async(db, cal.consultant) if cal.consultant else f"id-{cal.consultant_id}"
        bookings_count = (
            await db.execute(select(func.count(Booking.id)).where(Booking.calendar_id == cal.id))
        ).scalar() or 0
        rows.append(
            {
                "calendar": cal,
                "consultant": cal.consultant,
                "public_slug": slug,
                "bookings_count": int(bookings_count),
            }
        )
    return rows


async def set_calendar_active_async(db, calendar_id: int, *, is_active: bool) -> Calendar | None:
    cal = await db.get(Calendar, calendar_id)
    if not cal:
        return None
    cal.is_active = is_active
    await db.commit()
    return cal


async def list_failed_logins_async(db, *, limit: int = 50) -> list[AdminAuditLog]:
    from sqlalchemy import select

    result = await db.execute(
        select(AdminAuditLog)
        .where(AdminAuditLog.action == "login_failed")
        .order_by(AdminAuditLog.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_security_events_async(db, *, limit: int = 30) -> list[AdminAuditLog]:
    from sqlalchemy import select

    security_actions = (
        "login_failed",
        "impersonate_start",
        "impersonate_stop",
        "user_block",
        "user_unblock",
    )
    result = await db.execute(
        select(AdminAuditLog)
        .where(AdminAuditLog.action.in_(security_actions))
        .order_by(AdminAuditLog.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def booking_admin_card_async(db, booking_id: int) -> dict[str, Any] | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    booking = (
        await db.execute(
            select(Booking)
            .options(
                selectinload(Booking.service),
                selectinload(Booking.calendar).selectinload(Calendar.consultant),
                selectinload(Booking.client_user),
                selectinload(Booking.client_card),
            )
            .where(Booking.id == booking_id)
        )
    ).scalar_one_or_none()
    if not booking:
        return None
    return {"booking": booking, "status_labels": STATUS_LABELS}

