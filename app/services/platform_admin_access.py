"""RBAC helpers for platform admin routes and navigation."""
from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.session import AuthUser
from app.services.admin_rbac import (
    PERM_AUDIT,
    PERM_BILLING,
    PERM_BROADCAST,
    PERM_ERRORS,
    PERM_OPS,
    PERM_SETTINGS,
    PERM_SUPPORT,
    PERM_USERS_READ,
    PERM_USERS_WRITE,
    has_permission,
)

NAV_PERMISSIONS: dict[str, str | None] = {
    "dashboard": PERM_USERS_READ,
    "users": PERM_USERS_READ,
    "specialists": PERM_USERS_READ,
    "clients": PERM_USERS_READ,
    "bookings": PERM_USERS_READ,
    "calendars": PERM_USERS_READ,
    "telegram": PERM_BROADCAST,
    "support": PERM_SUPPORT,
    "billing": PERM_BILLING,
    "errors": PERM_ERRORS,
    "security": None,
    "email": PERM_SETTINGS,
    "analytics": PERM_USERS_READ,
    "settings": PERM_SETTINGS,
    "audit": PERM_AUDIT,
    "ops": PERM_OPS,
}


def admin_permissions(db: Session, user: AuthUser) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for nav, perm in NAV_PERMISSIONS.items():
        if perm is None:
            out[nav] = True
        else:
            out[nav] = has_permission(db, user, perm)
    out["users_write"] = has_permission(db, user, PERM_USERS_WRITE)
    out["security"] = True
    return out


def require_admin_permission(db: Session, user: AuthUser, permission: str) -> None:
    if not has_permission(db, user, permission):
        raise HTTPException(status_code=403, detail="Недостаточно прав для этого раздела")


_HOME_FALLBACK: tuple[tuple[str, str], ...] = (
    ("errors", "/platform-admin/errors/"),
    ("support", "/platform-admin/support/"),
    ("ops", "/platform-admin/ops/"),
    ("audit", "/platform-admin/audit/"),
    ("telegram", "/platform-admin/telegram/"),
    ("billing", "/platform-admin/billing/"),
    ("settings", "/platform-admin/settings/"),
    ("users", "/platform-admin/users/"),
)


def admin_home_url(db: Session, user: AuthUser) -> str:
    """Landing URL for /platform-admin/ based on RBAC (developer → errors, etc.)."""
    perms = admin_permissions(db, user)
    if perms.get("dashboard"):
        return "/platform-admin/"
    for key, url in _HOME_FALLBACK:
        if perms.get(key):
            return url
    return "/platform-admin/security/"
