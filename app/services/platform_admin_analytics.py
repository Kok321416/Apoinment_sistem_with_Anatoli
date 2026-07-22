"""Platform analytics: DAU/WAU and signup trends (Admin A4)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, PlatformUserActivity, User


def analytics_snapshot(db: Session) -> dict:
    today = date.today()
    week_start = today - timedelta(days=6)
    month_start = today - timedelta(days=29)

    dau = (
        db.query(func.count(func.distinct(PlatformUserActivity.user_id)))
        .filter(PlatformUserActivity.activity_date == today)
        .scalar()
        or 0
    )
    wau = (
        db.query(func.count(func.distinct(PlatformUserActivity.user_id)))
        .filter(PlatformUserActivity.activity_date >= week_start)
        .scalar()
        or 0
    )
    mau = (
        db.query(func.count(func.distinct(PlatformUserActivity.user_id)))
        .filter(PlatformUserActivity.activity_date >= month_start)
        .scalar()
        or 0
    )

    signups_today = (
        db.query(func.count(User.id))
        .filter(User.date_joined >= datetime.combine(today, datetime.min.time()))
        .scalar()
        or 0
    )
    signups_week = (
        db.query(func.count(User.id))
        .filter(User.date_joined >= datetime.combine(week_start, datetime.min.time()))
        .scalar()
        or 0
    )

    bookings_week = (
        db.query(func.count(Booking.id)).filter(Booking.booking_date >= week_start).scalar() or 0
    )

    daily_active = _daily_counts(
        db,
        PlatformUserActivity.activity_date,
        PlatformUserActivity.user_id,
        week_start,
        today,
        distinct_users=True,
    )
    daily_signups = _daily_counts(
        db,
        func.date(User.date_joined),
        User.id,
        week_start,
        today,
        distinct_users=False,
    )
    daily_bookings = _daily_counts(
        db,
        Booking.booking_date,
        Booking.id,
        week_start,
        today,
        distinct_users=False,
    )

    return {
        "dau": int(dau),
        "wau": int(wau),
        "mau": int(mau),
        "signups_today": int(signups_today),
        "signups_week": int(signups_week),
        "bookings_week": int(bookings_week),
        "daily_active": daily_active,
        "daily_signups": daily_signups,
        "daily_bookings": daily_bookings,
    }


def _daily_counts(
    db: Session,
    date_col,
    count_col,
    start: date,
    end: date,
    *,
    distinct_users: bool,
) -> list[dict]:
    if distinct_users:
        agg = func.count(func.distinct(count_col))
    else:
        agg = func.count(count_col)
    rows = (
        db.query(date_col, agg)
        .filter(date_col >= start, date_col <= end)
        .group_by(date_col)
        .order_by(date_col.asc())
        .all()
    )
    by_date = {str(r[0]): int(r[1] or 0) for r in rows}
    out = []
    d = start
    while d <= end:
        key = str(d)
        out.append({"date": key, "value": by_date.get(key, 0)})
        d += timedelta(days=1)
    return out
