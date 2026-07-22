"""Admin Ctrl+K global search."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.auth.session import AuthUser
from app.services.admin_rbac import (
    PERM_ERRORS,
    PERM_SUPPORT,
    PERM_USERS_READ,
    has_permission,
)
from app.services.platform_admin_domain import list_bookings, search_platform_clients, search_specialists
from app.services.platform_admin_users import search_users
from app.services.platform_admin_access import admin_permissions
from app.services.platform_support import list_support_tickets


def admin_global_search(db: Session, user: AuthUser, q: str, *, limit_per_type: int = 5) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if len(q) < 2:
        return _nav_shortcuts(db, user, q)

    results: list[dict[str, Any]] = []

    if has_permission(db, user, PERM_USERS_READ):
        for u in search_users(db, q, limit=limit_per_type):
            label = u.email or u.username
            name = f"{u.first_name} {u.last_name}".strip()
            if name:
                label = f"{name} · {label}"
            results.append(
                {
                    "type": "user",
                    "id": u.id,
                    "title": label,
                    "subtitle": f"User #{u.id}",
                    "url": f"/platform-admin/users/{u.id}/",
                }
            )

        for row in search_specialists(db, q, limit=limit_per_type):
            c = row["consultant"]
            results.append(
                {
                    "type": "specialist",
                    "id": c.id,
                    "title": f"{c.first_name} {c.last_name}".strip() or f"Consultant #{c.id}",
                    "subtitle": f"Специалист · {row.get('bookings_total', 0)} записей",
                    "url": f"/platform-admin/specialists/{c.id}/",
                }
            )

        for row in search_platform_clients(db, q, limit=limit_per_type):
            uid = row.get("client_user_id")
            cid = row.get("client_card_id")
            if uid:
                url = f"/platform-admin/clients/user/{uid}/"
            elif cid:
                url = f"/platform-admin/clients/card/{cid}/"
            else:
                continue
            results.append(
                {
                    "type": "client",
                    "id": uid or cid,
                    "title": row.get("name") or "-",
                    "subtitle": "Клиент",
                    "url": url,
                }
            )

        for b in list_bookings(db, q=q, limit=limit_per_type):
            results.append(
                {
                    "type": "booking",
                    "id": b.id,
                    "title": f"#{b.id} {b.client_name}",
                    "subtitle": f"{b.booking_date} {b.booking_time} · {b.status}",
                    "url": f"/platform-admin/bookings/{b.id}/",
                }
            )

    if has_permission(db, user, PERM_SUPPORT):
        for t in list_support_tickets(db, q=q, limit=limit_per_type):
            results.append(
                {
                    "type": "support",
                    "id": t.id,
                    "title": t.subject,
                    "subtitle": f"Тикет · {t.contact_email} · {t.status}",
                    "url": f"/platform-admin/support/{t.id}/",
                }
            )

    if has_permission(db, user, PERM_ERRORS) and q.isdigit():
        from app.models import PlatformErrorLog

        err = db.get(PlatformErrorLog, int(q))
        if err:
            results.append(
                {
                    "type": "error",
                    "id": err.id,
                    "title": err.message or f"Error #{err.id}",
                    "subtitle": f"{err.method} {err.path or ''} · {err.status}",
                    "url": f"/platform-admin/errors/?status={err.status}",
                }
            )

    return results[:25]


def _nav_shortcuts(db: Session, user: AuthUser, q: str) -> list[dict[str, Any]]:
    if q:
        return []
    perms = admin_permissions(db, user)
    shortcuts: tuple[tuple[str, str, str], ...] = (
        ("users", "Пользователи", "/platform-admin/users/"),
        ("bookings", "Записи", "/platform-admin/bookings/"),
        ("bookings", "Календарь записей", "/platform-admin/bookings/calendar/"),
        ("telegram", "Telegram", "/platform-admin/telegram/"),
        ("support", "Поддержка", "/platform-admin/support/"),
        ("errors", "Ошибки", "/platform-admin/errors/"),
        ("ops", "Ops", "/platform-admin/ops/"),
        ("audit", "Audit", "/platform-admin/audit/"),
        ("settings", "Настройки", "/platform-admin/settings/"),
        ("billing", "Биллинг", "/platform-admin/billing/"),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, title, url in shortcuts:
        if not perms.get(key) or url in seen:
            continue
        seen.add(url)
        out.append({"type": "nav", "title": title, "subtitle": "Раздел", "url": url})
    return out
