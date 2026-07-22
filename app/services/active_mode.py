"""Session active_mode for dual-role site UX (Phase 6)."""
from __future__ import annotations

from datetime import date, time
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Consultant, SocialAccount
from app.models.core import Booking

MODE_CLIENT = "client"
MODE_SPECIALIST = "specialist"
VALID_MODES = frozenset({MODE_CLIENT, MODE_SPECIALIST})


def user_has_consultant(db: Session, user_id: int) -> bool:
    return db.query(Consultant.id).filter(Consultant.user_id == user_id).first() is not None


def get_cached_has_consultant(request: Request, db: Session, user_id: int) -> bool:
    """Prefer session flag to avoid Consultant EXISTS on every page render."""
    if "session" in request.scope and "has_consultant" in request.session:
        return bool(request.session.get("has_consultant"))
    has_c = user_has_consultant(db, user_id)
    if "session" in request.scope:
        request.session["has_consultant"] = has_c
    return has_c


def default_mode_for_user(db: Session, user_id: int) -> str:
    return MODE_SPECIALIST if user_has_consultant(db, user_id) else MODE_CLIENT


def get_active_mode(
    request: Request,
    db: Session,
    user_id: int | None,
    *,
    has_consultant: bool | None = None,
) -> str:
    if not user_id or "session" not in request.scope:
        return MODE_CLIENT
    raw = (request.session.get("active_mode") or "").strip().lower()
    if raw in VALID_MODES:
        if raw == MODE_SPECIALIST:
            if has_consultant is None:
                has_consultant = get_cached_has_consultant(request, db, user_id)
            if not has_consultant:
                return MODE_CLIENT
        return raw
    if has_consultant is None:
        has_consultant = get_cached_has_consultant(request, db, user_id)
    mode = MODE_SPECIALIST if has_consultant else MODE_CLIENT
    request.session["active_mode"] = mode
    return mode


def set_active_mode(request: Request, mode: str, *, has_consultant: bool) -> str:
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        mode = MODE_CLIENT
    if mode == MODE_SPECIALIST and not has_consultant:
        mode = MODE_CLIENT
    if "session" in request.scope:
        request.session["active_mode"] = mode
        request.session["has_consultant"] = bool(has_consultant)
    return mode


def list_client_bookings(db: Session, user_id: int, *, limit: int = 100) -> list[Booking]:
    """Bookings where the user is the client (client_user_id or matching Telegram SocialAccount)."""
    q = (
        db.query(Booking)
        .filter(Booking.client_user_id == user_id)
        .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
    )
    by_user = q.limit(limit).all()
    seen = {b.id for b in by_user}

    sa = (
        db.query(SocialAccount)
        .filter(SocialAccount.provider == "telegram", SocialAccount.user_id == user_id)
        .first()
    )
    extras: list[Booking] = []
    if sa and (sa.uid or "").strip():
        try:
            tid = int(str(sa.uid).strip())
        except ValueError:
            tid = None
        if tid is not None:
            for b in (
                db.query(Booking)
                .filter(Booking.telegram_id == tid, Booking.client_user_id.is_(None))
                .order_by(Booking.booking_date.desc(), Booking.booking_time.desc())
                .limit(limit)
                .all()
            ):
                if b.id not in seen:
                    extras.append(b)
                    seen.add(b.id)
    merged = by_user + extras
    merged.sort(
        key=lambda b: (b.booking_date or date.min, b.booking_time or time.min),
        reverse=True,
    )
    return merged[:limit]
