"""Client CRM: dashboard stats, card serialization, badges."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, ClientCard

NEW_DAYS = 14
INACTIVE_DAYS = 90
VIP_BOOKINGS = 5
REGULAR_BOOKINGS = 2


def _text(value: str | None) -> str:
    return (value or "").strip()


def initials(name: str | None) -> str:
    parts = [p for p in _text(name).split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return "?"


def avatar_color(card_id: int) -> str:
    palette = ("#7d5cff", "#49d1ff", "#3be4c8", "#3b82f6", "#f5a623", "#ec4899")
    return palette[card_id % len(palette)]


def card_completeness(card: ClientCard) -> dict:
    checks = []
    score = 0
    fields = (
        ("name", "Имя", 20, _text(card.name)),
        ("phone", "Телефон", 25, _text(card.phone)),
        ("email", "Email", 25, _text(card.email)),
        ("telegram", "Telegram", 15, _text(card.telegram)),
        ("notes", "Заметки", 15, _text(card.notes)),
    )
    for key, label, weight, val in fields:
        done = bool(val)
        if done:
            score += weight
        checks.append({"id": key, "label": label, "weight": weight, "done": done})
    percent = min(score, 100)
    missing = [c["label"] for c in checks if not c["done"]]
    return {"percent": percent, "checks": checks, "missing": missing[:3]}


def _derive_badge(
    card: ClientCard,
    booking_count: int,
    last_booking: date | None,
    today: date,
) -> str | None:
    if card.created_at and (today - card.created_at.date()).days <= NEW_DAYS:
        return "new"
    if booking_count >= VIP_BOOKINGS:
        return "vip"
    if last_booking and (today - last_booking).days > INACTIVE_DAYS:
        return "inactive"
    if booking_count == 0 and card.created_at and (today - card.created_at.date()).days > INACTIVE_DAYS:
        return "inactive"
    if booking_count >= REGULAR_BOOKINGS:
        return "regular"
    return None


def _badge_label(badge: str | None) -> str | None:
    return {
        "new": "Новый",
        "vip": "VIP",
        "regular": "Постоянный",
        "inactive": "Неактивный",
    }.get(badge or "")


def _status_label(badge: str | None) -> tuple[str, str]:
    if badge == "inactive":
        return "inactive", "Неактивный"
    return "active", "Активный"


def _calendar_ids(db: Session, consultant_id: int) -> list[int]:
    rows = db.query(Calendar.id).filter(Calendar.consultant_id == consultant_id).all()
    return [r[0] for r in rows]


def booking_stats(db: Session, consultant_id: int, card_ids: list[int]) -> dict[int, dict]:
    cal_ids = _calendar_ids(db, consultant_id)
    if not cal_ids or not card_ids:
        return {}
    rows = (
        db.query(
            Booking.client_card_id,
            func.count(Booking.id),
            func.max(Booking.booking_date),
        )
        .filter(
            Booking.calendar_id.in_(cal_ids),
            Booking.client_card_id.in_(card_ids),
        )
        .group_by(Booking.client_card_id)
        .all()
    )
    return {
        cid: {"booking_count": cnt, "last_booking": last_date}
        for cid, cnt, last_date in rows
        if cid is not None
    }


def consultant_booking_counts(db: Session, consultant_id: int) -> tuple[int, int]:
    cal_ids = _calendar_ids(db, consultant_id)
    if not cal_ids:
        return 0, 0
    today = date.today()
    today_count = (
        db.query(func.count(Booking.id))
        .filter(Booking.calendar_id.in_(cal_ids), Booking.booking_date == today)
        .scalar()
    ) or 0
    upcoming = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.calendar_id.in_(cal_ids),
            Booking.booking_date >= today,
            Booking.status.in_(["pending", "confirmed"]),
        )
        .scalar()
    ) or 0
    return today_count, upcoming


def dashboard_stats(db: Session, consultant_id: int, cards: list[ClientCard]) -> dict:
    today = date.today()
    total = len(cards)
    new_count = sum(
        1 for c in cards
        if c.created_at and (today - c.created_at.date()).days <= NEW_DAYS
    )
    today_bookings, upcoming = consultant_booking_counts(db, consultant_id)
    completeness_vals = [card_completeness(c)["percent"] for c in cards]
    avg_completeness = round(sum(completeness_vals) / total) if total else 0
    last_updated = max((c.updated_at for c in cards if c.updated_at), default=None)
    last_created = max((c.created_at for c in cards if c.created_at), default=None)
    return {
        "total": total,
        "new_count": new_count,
        "today_bookings": today_bookings,
        "upcoming": upcoming,
        "avg_completeness": avg_completeness,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "last_created": last_created.isoformat() if last_created else None,
    }


def serialize_card(card: ClientCard, stats: dict, today: date | None = None) -> dict:
    today = today or date.today()
    bstats = stats.get(card.id, {})
    booking_count = bstats.get("booking_count", 0)
    last_booking = bstats.get("last_booking")
    badge = _derive_badge(card, booking_count, last_booking, today)
    status_key, status_label = _status_label(badge)
    comp = card_completeness(card)
    display_name = _text(card.name) or f"Клиент #{card.id}"
    return {
        "id": card.id,
        "name": display_name,
        "email": _text(card.email),
        "phone": _text(card.phone),
        "telegram": _text(card.telegram),
        "notes": _text(card.notes),
        "initials": initials(card.name),
        "avatar_color": avatar_color(card.id),
        "booking_count": booking_count,
        "last_booking": last_booking.isoformat() if last_booking else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
        "badge": badge,
        "badge_label": _badge_label(badge),
        "status": status_key,
        "status_label": status_label,
        "completeness": comp,
        "detail_url": f"/clients/{card.id}/",
    }


def recent_activity(cards: list[ClientCard], limit: int = 8) -> list[dict]:
    sorted_cards = sorted(
        cards,
        key=lambda c: c.updated_at or c.created_at or datetime.min,
        reverse=True,
    )
    activity = []
    for card in sorted_cards[:limit]:
        ts = card.updated_at or card.created_at
        action = "обновлена" if card.updated_at and card.created_at and card.updated_at > card.created_at else "создана"
        activity.append({
            "id": card.id,
            "name": _text(card.name) or f"Клиент #{card.id}",
            "action": action,
            "at": ts.isoformat() if ts else None,
        })
    return activity


def build_crm_payload(db: Session, consultant_id: int, cards: list[ClientCard]) -> dict:
    card_ids = [c.id for c in cards]
    stats = booking_stats(db, consultant_id, card_ids)
    today = date.today()
    serialized = [serialize_card(c, stats, today) for c in cards]
    dash = dashboard_stats(db, consultant_id, cards)
    return {
        "dashboard": dash,
        "clients": serialized,
        "activity": recent_activity(cards),
    }
