"""Platform admin RBAC (schema + permission helpers)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.session import AuthUser
from app.models import AdminRoleAssignment, User

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMINISTRATOR = "administrator"
ROLE_SUPPORT = "support"
ROLE_FINANCE = "finance"
ROLE_MODERATOR = "moderator"
ROLE_DEVELOPER = "developer"
ROLE_VIEWER = "viewer"

ASSIGNABLE_ROLES = (
    ROLE_ADMINISTRATOR,
    ROLE_SUPPORT,
    ROLE_FINANCE,
    ROLE_MODERATOR,
    ROLE_DEVELOPER,
    ROLE_VIEWER,
)

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "Super Admin",
    ROLE_ADMINISTRATOR: "Administrator",
    ROLE_SUPPORT: "Support",
    ROLE_FINANCE: "Finance",
    ROLE_MODERATOR: "Moderator",
    ROLE_DEVELOPER: "Developer",
    ROLE_VIEWER: "Viewer",
}

PERM_USERS_READ = "users_read"
PERM_USERS_WRITE = "users_write"
PERM_IMPERSONATE = "impersonate"
PERM_BROADCAST = "broadcast"
PERM_SUPPORT = "support"
PERM_BILLING = "billing"
PERM_SETTINGS = "settings"
PERM_OPS = "ops"
PERM_ERRORS = "errors"
PERM_AUDIT = "audit"

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_SUPER_ADMIN: frozenset(
        {
            PERM_USERS_READ,
            PERM_USERS_WRITE,
            PERM_IMPERSONATE,
            PERM_BROADCAST,
            PERM_SUPPORT,
            PERM_BILLING,
            PERM_SETTINGS,
            PERM_OPS,
            PERM_ERRORS,
            PERM_AUDIT,
        }
    ),
    ROLE_ADMINISTRATOR: frozenset(
        {
            PERM_USERS_READ,
            PERM_USERS_WRITE,
            PERM_BROADCAST,
            PERM_SUPPORT,
            PERM_BILLING,
            PERM_SETTINGS,
            PERM_OPS,
            PERM_ERRORS,
            PERM_AUDIT,
        }
    ),
    ROLE_SUPPORT: frozenset({PERM_USERS_READ, PERM_USERS_WRITE, PERM_SUPPORT}),
    ROLE_FINANCE: frozenset({PERM_USERS_READ, PERM_BILLING, PERM_AUDIT}),
    ROLE_MODERATOR: frozenset({PERM_USERS_READ, PERM_USERS_WRITE}),
    ROLE_DEVELOPER: frozenset({PERM_ERRORS, PERM_OPS, PERM_AUDIT}),
    ROLE_VIEWER: frozenset({PERM_USERS_READ, PERM_AUDIT}),
}


def list_role_assignments(db: Session, user_id: int) -> list[AdminRoleAssignment]:
    return (
        db.query(AdminRoleAssignment)
        .filter(AdminRoleAssignment.user_id == user_id)
        .order_by(AdminRoleAssignment.role.asc())
        .all()
    )


def effective_roles(db: Session, user: User | AuthUser) -> set[str]:
    if user.is_superuser:
        return {ROLE_SUPER_ADMIN}
    roles: set[str] = set()
    if user.is_staff:
        rows = db.query(AdminRoleAssignment.role).filter(AdminRoleAssignment.user_id == user.id).all()
        roles = {r[0] for r in rows}
        if not roles:
            roles.add(ROLE_ADMINISTRATOR)
    return roles


def has_permission(db: Session, user: User | AuthUser, permission: str) -> bool:
    if not getattr(user, "is_platform_admin", None):
        if not (user.is_staff or user.is_superuser):
            return False
    for role in effective_roles(db, user):
        if permission in _ROLE_PERMISSIONS.get(role, frozenset()):
            return True
    return False


def assign_role(db: Session, *, user_id: int, role: str, granted_by: int) -> tuple[bool, str]:
    if role not in ASSIGNABLE_ROLES:
        return False, "Некорректная роль"
    target = db.get(User, user_id)
    if not target or not target.is_staff:
        return False, "Роли назначаются только staff-пользователям"
    exists = (
        db.query(AdminRoleAssignment)
        .filter(AdminRoleAssignment.user_id == user_id, AdminRoleAssignment.role == role)
        .first()
    )
    if exists:
        return False, "Роль уже назначена"
    db.add(AdminRoleAssignment(user_id=user_id, role=role, granted_by_user_id=granted_by))
    db.commit()
    return True, "Роль назначена"


def revoke_role(db: Session, *, user_id: int, role: str) -> tuple[bool, str]:
    row = (
        db.query(AdminRoleAssignment)
        .filter(AdminRoleAssignment.user_id == user_id, AdminRoleAssignment.role == role)
        .first()
    )
    if not row:
        return False, "Роль не найдена"
    db.delete(row)
    db.commit()
    return True, "Роль снята"
