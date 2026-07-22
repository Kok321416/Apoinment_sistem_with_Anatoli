from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth.passwords import has_usable_password
from app.models.auth import User


@dataclass
class AuthUser:
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    is_active: bool
    password_hash: str
    is_staff: bool = False
    is_superuser: bool = False

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def has_usable_password(self) -> bool:
        return has_usable_password(self.password_hash)

    @property
    def is_platform_admin(self) -> bool:
        return bool(self.is_staff or self.is_superuser)

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def user_from_model(user: User | None) -> AuthUser | None:
    if not user or not user.is_active:
        return None
    return AuthUser(
        id=user.id,
        username=user.username,
        email=user.email or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        is_active=user.is_active,
        password_hash=user.password or "",
        is_staff=bool(getattr(user, "is_staff", False)),
        is_superuser=bool(getattr(user, "is_superuser", False)),
    )


def get_session_user_id(request: Request) -> int | None:
    if "session" not in request.scope:
        return None
    return request.session.get("user_id")


def login_user(request: Request, user: User) -> None:
    if "session" in request.scope:
        request.session["user_id"] = user.id
        request.session.pop("impersonator_id", None)


def start_impersonation(request: Request, *, admin_user_id: int, target_user_id: int) -> None:
    if "session" not in request.scope:
        return
    request.session["impersonator_id"] = admin_user_id
    request.session["user_id"] = target_user_id
    request.session.pop("active_mode", None)


def stop_impersonation(request: Request) -> int | None:
    """Restore admin session. Returns admin user id or None."""
    if "session" not in request.scope:
        return None
    admin_id = request.session.pop("impersonator_id", None)
    if admin_id:
        request.session["user_id"] = admin_id
        request.session.pop("active_mode", None)
    return admin_id


def get_impersonator_id(request: Request) -> int | None:
    if "session" not in request.scope:
        return None
    return request.session.get("impersonator_id")


def logout_user(request: Request) -> None:
    if "session" not in request.scope:
        return
    request.session.pop("user_id", None)
    request.session.pop("impersonator_id", None)
    request.session.pop("active_mode", None)
    request.session.pop("register_fio", None)
    request.session.pop("register_phone", None)
    request.session.pop("google_calendar_oauth_state", None)
    request.session.pop("yandex_oauth_state", None)
    request.session.pop("yandex_oauth_process", None)
    request.session.pop("yandex_oauth_next", None)
    request.session.pop("yandex_connect_user_id", None)
    request.session.pop("integrations_success", None)
    request.session.pop("integrations_error", None)


def get_current_user(request: Request, db: Session) -> AuthUser | None:
    user_id = get_session_user_id(request)
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user_from_model(user)
