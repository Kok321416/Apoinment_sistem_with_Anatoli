"""EXPLAIN helpers for hot-path acceptance (Phase E). Read-only."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Representative queries (MySQL/SQLite). Bind params as plain literals for EXPLAIN only.
HOT_QUERIES: dict[str, str] = {
    "bookings_by_calendar_date_status": (
        "SELECT id FROM bookings "
        "WHERE calendar_id = 1 AND booking_date = CURRENT_DATE AND status IN ('pending','confirmed') "
        "LIMIT 50"
    ),
    "time_slots_by_calendar_dow": (
        "SELECT id FROM time_slots "
        "WHERE calendar_id = 1 AND day_of_week = 1 AND is_available = 1 "
        "LIMIT 50"
    ),
    "bookings_by_telegram_id": (
        "SELECT id FROM bookings WHERE telegram_id = 1 AND status != 'cancelled' "
        "ORDER BY booking_date DESC LIMIT 20"
    ),
    "calendars_by_consultant": (
        "SELECT id FROM calendars WHERE consultant_id = 1 AND is_active = 1"
    ),
    "services_by_consultant": (
        "SELECT id FROM services WHERE consultant_id = 1 AND is_active = 1 "
        "ORDER BY sort_order, name LIMIT 100"
    ),
    "social_by_provider_uid": (
        "SELECT id FROM socialaccount_socialaccount "
        "WHERE provider = 'telegram' AND uid = '1' LIMIT 1"
    ),
    "consultant_by_user": ("SELECT id FROM consultants WHERE user_id = 1 LIMIT 1"),
    "integration_by_chat": (
        "SELECT id FROM integrations WHERE telegram_chat_id = '1' LIMIT 1"
    ),
}


def explain_hot_queries(db: Session) -> dict:
    """Run EXPLAIN on hot queries; never raises — returns per-query rows or error."""
    out: dict[str, dict] = {}
    for name, sql in HOT_QUERIES.items():
        try:
            rows = db.execute(text(f"EXPLAIN {sql}")).mappings().all()
            out[name] = {"ok": True, "plan": [dict(r) for r in rows]}
        except Exception as exc:
            out[name] = {"ok": False, "error": str(exc)[:240]}
    return out


def list_expected_indexes() -> list[dict[str, str]]:
    return [
        {"table": "bookings", "name": "ix_bookings_calendar_date_status"},
        {"table": "bookings", "name": "ix_bookings_telegram_id"},
        {"table": "bookings", "name": "ix_bookings_status_date"},
        {"table": "time_slots", "name": "ix_time_slots_calendar_dow"},
        {"table": "calendars", "name": "ix_calendars_consultant_active"},
        {"table": "services", "name": "ix_services_consultant_active"},
        {"table": "services", "name": "ix_services_calendar_id"},
        {"table": "consultants", "name": "ix_consultants_user_id"},
        {"table": "consultants", "name": "ix_consultants_public_slug"},
        {"table": "socialaccount_socialaccount", "name": "ix_socialaccount_provider_uid"},
        {"table": "socialaccount_socialaccount", "name": "ix_socialaccount_user_id"},
        {"table": "integrations", "name": "ix_integrations_telegram_chat_id"},
        {"table": "consultant_client_cards", "name": "ix_client_cards_consultant_id"},
    ]
