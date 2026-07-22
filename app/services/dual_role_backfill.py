"""Phase 2: backfill Booking.client_user_id from telegram_id via SocialAccount.

Does NOT create Users. Skips ambiguous telegram uids linked to multiple users.

Run:
  python -m app.commands.dual_role_backfill --dry-run
  python -m app.commands.dual_role_backfill
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import Booking, SocialAccount


def _norm_uid(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def build_telegram_uid_to_user_ids(db: Session) -> dict[str, set[int]]:
    mapping: dict[str, set[int]] = defaultdict(set)
    rows = (
        db.query(SocialAccount.uid, SocialAccount.user_id)
        .filter(SocialAccount.provider == "telegram")
        .all()
    )
    for uid, user_id in rows:
        key = _norm_uid(uid)
        if key and user_id is not None:
            mapping[key].add(int(user_id))
    return mapping


def backfill_booking_client_user_ids(
    db: Session,
    *,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Set Booking.client_user_id where telegram_id matches exactly one User via SocialAccount.

    Idempotent: rows that already have client_user_id are left unchanged.
    """
    uid_map = build_telegram_uid_to_user_ids(db)
    q = (
        db.query(Booking)
        .filter(Booking.telegram_id.isnot(None))
        .filter(Booking.client_user_id.is_(None))
        .order_by(Booking.id.asc())
    )
    if limit is not None:
        q = q.limit(int(limit))
    bookings = q.all()

    updated = 0
    skipped_no_user = 0
    skipped_ambiguous = 0
    samples_updated: list[dict[str, int]] = []
    samples_ambiguous: list[dict[str, Any]] = []

    for booking in bookings:
        key = _norm_uid(booking.telegram_id)
        if not key:
            skipped_no_user += 1
            continue
        user_ids = uid_map.get(key) or set()
        if len(user_ids) == 0:
            skipped_no_user += 1
            continue
        if len(user_ids) > 1:
            skipped_ambiguous += 1
            if len(samples_ambiguous) < 20:
                samples_ambiguous.append(
                    {"booking_id": int(booking.id), "telegram_id": key, "user_ids": sorted(user_ids)}
                )
            continue
        user_id = next(iter(user_ids))
        if not dry_run:
            booking.client_user_id = user_id
        updated += 1
        if len(samples_updated) < 20:
            samples_updated.append({"booking_id": int(booking.id), "user_id": user_id})

    if not dry_run and updated:
        db.commit()

    return {
        "dry_run": dry_run,
        "candidates": len(bookings),
        "updated": updated,
        "skipped_no_user": skipped_no_user,
        "skipped_ambiguous": skipped_ambiguous,
        "samples_updated": samples_updated,
        "samples_ambiguous": samples_ambiguous,
    }


def resolve_client_user_id_for_telegram(db: Session, telegram_id: Any) -> int | None:
    """Return User.id if telegram_id maps to exactly one SocialAccount user, else None."""
    key = _norm_uid(telegram_id)
    if not key:
        return None
    variants = {key}
    if key.isdigit():
        variants.add(str(int(key)))
    rows = (
        db.query(SocialAccount.user_id)
        .filter(SocialAccount.provider == "telegram", SocialAccount.uid.in_(list(variants)))
        .all()
    )
    user_ids = {int(r[0]) for r in rows if r[0] is not None}
    if len(user_ids) == 1:
        return next(iter(user_ids))
    return None


def format_backfill_report(data: dict[str, Any]) -> str:
    mode = "DRY-RUN" if data.get("dry_run") else "APPLY"
    lines = [
        f"=== Dual-role backfill Phase 2 ({mode}) ===",
        f"Candidates (telegram_id set, client_user_id empty): {data['candidates']}",
        f"Would update / updated: {data['updated']}",
        f"Skipped (no matching User): {data['skipped_no_user']}",
        f"Skipped (ambiguous uid -> many users): {data['skipped_ambiguous']}",
        f"Samples updated: {data['samples_updated']}",
        f"Samples ambiguous: {data['samples_ambiguous']}",
        "=== end ===",
    ]
    return "\n".join(lines)
