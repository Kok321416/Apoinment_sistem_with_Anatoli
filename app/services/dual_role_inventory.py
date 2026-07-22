"""Phase 0: read-only dual-role inventory.

Run: python -m app.commands.dual_role_inventory
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Booking, Consultant, Integration, SocialAccount, User
from app.services.app_counters import DEDUP_HITS_KEY, get_counter


def _norm_chat(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s


def collect_dual_role_inventory(db: Session) -> dict[str, Any]:
    """Return counts and sample IDs for dual-role migration planning. Read-only."""
    users_total = db.query(func.count(User.id)).scalar() or 0
    consultants_total = db.query(func.count(Consultant.id)).scalar() or 0
    consultants_with_user = (
        db.query(func.count(Consultant.id)).filter(Consultant.user_id.isnot(None)).scalar() or 0
    )
    orphan_user_ids = [
        row[0]
        for row in (
            db.query(User.id)
            .outerjoin(Consultant, Consultant.user_id == User.id)
            .filter(Consultant.id.is_(None))
            .limit(50)
            .all()
        )
    ]
    orphan_users_count = (
        db.query(func.count(User.id))
        .outerjoin(Consultant, Consultant.user_id == User.id)
        .filter(Consultant.id.is_(None))
        .scalar()
        or 0
    )

    # Shared Integration.telegram_chat_id
    chat_rows = (
        db.query(Integration.telegram_chat_id, Integration.consultant_id)
        .filter(Integration.telegram_chat_id.isnot(None))
        .filter(Integration.telegram_chat_id != "")
        .all()
    )
    chat_counter: Counter[str] = Counter()
    chat_to_consultants: dict[str, list[int]] = {}
    for chat_id, consultant_id in chat_rows:
        key = _norm_chat(chat_id)
        if not key:
            continue
        chat_counter[key] += 1
        chat_to_consultants.setdefault(key, []).append(int(consultant_id))
    shared_chats = {
        chat: consultants
        for chat, consultants in chat_to_consultants.items()
        if chat_counter[chat] > 1
    }

    # Bookings with telegram_id that also match an Integration chat (already dual channel)
    integration_chats = set(chat_to_consultants.keys())
    bookings_with_tg = (
        db.query(Booking.id, Booking.telegram_id)
        .filter(Booking.telegram_id.isnot(None))
        .all()
    )
    dual_channel_booking_ids: list[int] = []
    for booking_id, telegram_id in bookings_with_tg:
        key = _norm_chat(telegram_id)
        if key and key in integration_chats:
            dual_channel_booking_ids.append(int(booking_id))

    # Bookings linkable to User via SocialAccount(telegram)
    sa_rows = (
        db.query(SocialAccount.uid, SocialAccount.user_id, SocialAccount.id)
        .filter(SocialAccount.provider == "telegram")
        .all()
    )
    uid_counter: Counter[str] = Counter()
    uid_to_users: dict[str, set[int]] = {}
    for uid, user_id, _sa_id in sa_rows:
        key = _norm_chat(uid)
        if not key:
            continue
        uid_counter[key] += 1
        uid_to_users.setdefault(key, set()).add(int(user_id))
    duplicate_social_uids = {
        uid: sorted(users) for uid, users in uid_to_users.items() if uid_counter[uid] > 1
    }

    linkable = 0
    already_linked = 0
    has_client_user_col = hasattr(Booking, "client_user_id")
    for booking_id, telegram_id in bookings_with_tg:
        key = _norm_chat(telegram_id)
        if not key:
            continue
        if key in uid_to_users:
            linkable += 1
        if has_client_user_col:
            # cheap sample via attribute if loaded; count separately below
            pass

    if has_client_user_col:
        already_linked = (
            db.query(func.count(Booking.id)).filter(Booking.client_user_id.isnot(None)).scalar() or 0
        )

    bookings_tg_total = len(bookings_with_tg)
    bookings_tg_without_user = bookings_tg_total - linkable

    # Dual users: have Consultant profile AND client signal (client bookings or TG SocialAccount)
    consultant_user_ids = {
        int(r[0])
        for r in db.query(Consultant.user_id).filter(Consultant.user_id.isnot(None)).all()
        if r[0] is not None
    }
    client_user_ids: set[int] = set()
    if has_client_user_col:
        client_user_ids |= {
            int(r[0])
            for r in db.query(Booking.client_user_id).filter(Booking.client_user_id.isnot(None)).distinct().all()
            if r[0] is not None
        }
    client_user_ids |= {
        int(r[0])
        for r in db.query(SocialAccount.user_id).filter(SocialAccount.provider == "telegram").all()
        if r[0] is not None
    }
    dual_user_ids = sorted(consultant_user_ids & client_user_ids)

    dedup_hits = 0
    try:
        dedup_hits = get_counter(db, DEDUP_HITS_KEY)
    except Exception:
        dedup_hits = 0

    return {
        "users_total": users_total,
        "consultants_total": consultants_total,
        "consultants_with_user": consultants_with_user,
        "orphan_users_count": orphan_users_count,
        "orphan_user_ids_sample": orphan_user_ids,
        "dual_users_count": len(dual_user_ids),
        "dual_user_ids_sample": dual_user_ids[:30],
        "notify_dedup_hits": dedup_hits,
        "integrations_with_chat": len(chat_rows),
        "shared_integration_chats_count": len(shared_chats),
        "shared_integration_chats_sample": {
            k: v for i, (k, v) in enumerate(shared_chats.items()) if i < 20
        },
        "bookings_with_telegram_id": bookings_tg_total,
        "dual_channel_bookings_count": len(dual_channel_booking_ids),
        "dual_channel_booking_ids_sample": dual_channel_booking_ids[:30],
        "telegram_social_accounts": len(sa_rows),
        "duplicate_telegram_social_uids_count": len(duplicate_social_uids),
        "duplicate_telegram_social_uids_sample": {
            k: v for i, (k, v) in enumerate(duplicate_social_uids.items()) if i < 20
        },
        "bookings_tg_linkable_via_social": linkable,
        "bookings_tg_without_matching_user": max(0, bookings_tg_without_user),
        "bookings_with_client_user_id": already_linked,
        "schema_has_client_user_id": has_client_user_col,
    }


def format_inventory_report(data: dict[str, Any]) -> str:
    lines = [
        "=== Dual-role inventory (Phase 0/9, read-only) ===",
        f"Users total: {data['users_total']}",
        f"Consultants total: {data['consultants_total']} (with user_id: {data['consultants_with_user']})",
        f"Orphan users (no Consultant): {data['orphan_users_count']}",
        f"  sample ids: {data['orphan_user_ids_sample']}",
        f"Dual users (consultant + client signal): {data['dual_users_count']}",
        f"  sample ids: {data['dual_user_ids_sample']}",
        f"Notify dedup hits (persisted): {data['notify_dedup_hits']}",
        f"Integrations with telegram_chat_id: {data['integrations_with_chat']}",
        f"SHARED integration chats: {data['shared_integration_chats_count']}",
        f"  sample: {data['shared_integration_chats_sample']}",
        f"Bookings with telegram_id: {data['bookings_with_telegram_id']}",
        f"Dual-channel bookings (tg_id == some Integration chat): {data['dual_channel_bookings_count']}",
        f"  sample booking ids: {data['dual_channel_booking_ids_sample']}",
        f"Telegram SocialAccounts: {data['telegram_social_accounts']}",
        f"Duplicate SocialAccount (provider,uid): {data['duplicate_telegram_social_uids_count']}",
        f"  sample: {data['duplicate_telegram_social_uids_sample']}",
        f"Bookings TG linkable via SocialAccount: {data['bookings_tg_linkable_via_social']}",
        f"Bookings TG without matching User: {data['bookings_tg_without_matching_user']}",
        f"schema_has_client_user_id: {data['schema_has_client_user_id']}",
        f"Bookings already with client_user_id: {data['bookings_with_client_user_id']}",
        "=== end ===",
    ]
    return "\n".join(lines)
