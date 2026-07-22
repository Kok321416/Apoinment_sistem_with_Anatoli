"""CSV export for admin (Admin A5)."""
from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models import Booking, Calendar, User


def export_users_csv(db: Session, *, limit: int = 5000) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "email", "username", "first_name", "last_name", "is_active", "is_staff", "date_joined"]
    )
    for u in db.query(User).order_by(User.id.asc()).limit(limit).all():
        writer.writerow(
            [
                u.id,
                u.email,
                u.username,
                u.first_name,
                u.last_name,
                int(u.is_active),
                int(u.is_staff),
                u.date_joined,
            ]
        )
    return buf.getvalue()


def export_bookings_csv(db: Session, *, limit: int = 5000) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "booking_date",
            "booking_time",
            "status",
            "client_name",
            "client_phone",
            "client_user_id",
            "consultant_id",
            "calendar_id",
            "service_name",
        ]
    )
    rows = (
        db.query(Booking)
        .options(joinedload(Booking.service), joinedload(Booking.calendar))
        .order_by(Booking.id.desc())
        .limit(limit)
        .all()
    )
    for b in rows:
        consultant_id = ""
        if b.calendar and isinstance(b.calendar, Calendar):
            consultant_id = b.calendar.consultant_id
        writer.writerow(
            [
                b.id,
                b.booking_date,
                b.booking_time,
                b.status,
                b.client_name,
                b.client_phone,
                b.client_user_id or "",
                consultant_id,
                b.calendar_id,
                b.service.name if b.service else "",
            ]
        )
    return buf.getvalue()


def export_filename(prefix: str) -> str:
    return f"{prefix}_{date.today().isoformat()}.csv"
