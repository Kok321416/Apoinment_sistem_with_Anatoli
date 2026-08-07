"""Admin A2: dashboard KPI and user search."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import Booking, Consultant, PlatformErrorLog, SocialAccount, User


def dashboard_kpi(db: Session) -> dict[str, int]:
    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    users_total = db.query(func.count(User.id)).scalar() or 0
    users_new_today = (
        db.query(func.count(User.id)).filter(User.date_joined >= day_start).scalar() or 0
    )
    consultants_total = db.query(func.count(Consultant.id)).scalar() or 0
    bookings_today = (
        db.query(func.count(Booking.id)).filter(Booking.booking_date == today).scalar() or 0
    )
    errors_new = (
        db.query(func.count(PlatformErrorLog.id))
        .filter(PlatformErrorLog.status == "new")
        .scalar()
        or 0
    )
    return {
        "users_total": int(users_total),
        "users_new_today": int(users_new_today),
        "consultants_total": int(consultants_total),
        "bookings_today": int(bookings_today),
        "errors_new": int(errors_new),
    }


def search_users(db: Session, q: str, *, limit: int = 50) -> list[User]:
    q = (q or "").strip()
    query = db.query(User).options(
        joinedload(User.consultant),
        joinedload(User.social_accounts),
    )
    if q:
        like = f"%{q}%"
        filters = [
            User.username.ilike(like),
            User.email.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ]
        if q.isdigit():
            filters.append(User.id == int(q))
        # telegram uid / phone via social or consultant
        sa_ids = [
            r[0]
            for r in db.query(SocialAccount.user_id)
            .filter(SocialAccount.uid.ilike(like))
            .limit(100)
            .all()
        ]
        if sa_ids:
            filters.append(User.id.in_(sa_ids))
        phone_ids = [
            r[0]
            for r in db.query(Consultant.user_id)
            .filter(Consultant.phone.ilike(like), Consultant.user_id.isnot(None))
            .limit(100)
            .all()
        ]
        if phone_ids:
            filters.append(User.id.in_(phone_ids))
        query = query.filter(or_(*filters))
    return query.order_by(User.id.desc()).limit(limit).all()


def user_admin_card(db: Session, user_id: int) -> dict[str, Any] | None:
    user = (
        db.query(User)
        .options(joinedload(User.consultant), joinedload(User.social_accounts))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        return None
    consultant = user.consultant
    social = [
        {"provider": sa.provider, "uid": sa.uid}
        for sa in (user.social_accounts or [])
    ]
    bookings_as_client = (
        db.query(func.count(Booking.id)).filter(Booking.client_user_id == user.id).scalar() or 0
    )
    return {
        "user": user,
        "consultant": consultant,
        "social": social,
        "bookings_as_client": int(bookings_as_client),
    }


async def dashboard_kpi_async(db) -> dict[str, int]:
    from sqlalchemy import func, select

    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    users_total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    users_new_today = (
        await db.execute(select(func.count(User.id)).where(User.date_joined >= day_start))
    ).scalar() or 0
    consultants_total = (await db.execute(select(func.count(Consultant.id)))).scalar() or 0
    bookings_today = (
        await db.execute(select(func.count(Booking.id)).where(Booking.booking_date == today))
    ).scalar() or 0
    from app.models import PlatformErrorLog

    errors_new = (
        await db.execute(
            select(func.count(PlatformErrorLog.id)).where(PlatformErrorLog.status == "new")
        )
    ).scalar() or 0
    return {
        "users_total": int(users_total),
        "users_new_today": int(users_new_today),
        "consultants_total": int(consultants_total),
        "bookings_today": int(bookings_today),
        "errors_new": int(errors_new),
    }


async def search_users_async(db, q: str, *, limit: int = 50) -> list[User]:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    q = (q or "").strip()
    stmt = select(User).options(
        selectinload(User.consultant),
        selectinload(User.social_accounts),
    )
    if q:
        like = f"%{q}%"
        filters = [
            User.username.ilike(like),
            User.email.ilike(like),
            User.first_name.ilike(like),
            User.last_name.ilike(like),
        ]
        if q.isdigit():
            filters.append(User.id == int(q))
        sa_ids = [
            r[0]
            for r in (
                await db.execute(
                    select(SocialAccount.user_id).where(SocialAccount.uid.ilike(like)).limit(100)
                )
            ).all()
        ]
        if sa_ids:
            filters.append(User.id.in_(sa_ids))
        phone_ids = [
            r[0]
            for r in (
                await db.execute(
                    select(Consultant.user_id)
                    .where(Consultant.phone.ilike(like), Consultant.user_id.isnot(None))
                    .limit(100)
                )
            ).all()
        ]
        if phone_ids:
            filters.append(User.id.in_(phone_ids))
        stmt = stmt.where(or_(*filters))
    result = await db.execute(stmt.order_by(User.id.desc()).limit(limit))
    return list(result.scalars().unique().all())


async def user_admin_card_async(db, user_id: int) -> dict[str, Any] | None:
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    user = (
        await db.execute(
            select(User)
            .options(selectinload(User.consultant), selectinload(User.social_accounts))
            .where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if not user:
        return None
    consultant = user.consultant
    social = [{"provider": sa.provider, "uid": sa.uid} for sa in (user.social_accounts or [])]
    bookings_as_client = (
        await db.execute(select(func.count(Booking.id)).where(Booking.client_user_id == user.id))
    ).scalar() or 0
    return {
        "user": user,
        "consultant": consultant,
        "social": social,
        "bookings_as_client": int(bookings_as_client),
    }
