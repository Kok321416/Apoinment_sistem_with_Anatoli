from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.auth.session import AuthUser, get_current_user
from app.database import get_async_db, get_db
from app.models import Consultant, User


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> AuthUser | None:
    return get_current_user(request, db)


def require_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login/"})
    return user


async def resolve_request_user_async(request: Request, db: AsyncSession) -> AuthUser | None:
    """Resolve cabinet user from session cookie, else Mini App Bearer fallback.

    Cookie session is primary for site + Mini App.
    Bearer (from /api/telegram/webapp-auth, TTL 15 min) is WebView fallback only.
    """
    from app.auth.session import get_current_user_async, user_from_model
    from app.services.miniapp_token import bearer_user_id

    user = await get_current_user_async(request, db)
    if user:
        return user
    uid = bearer_user_id(request.headers.get("authorization"))
    if not uid:
        return None
    return user_from_model(await db.get(User, uid))


async def get_optional_user_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> AuthUser | None:
    return await resolve_request_user_async(request, db)


async def require_user_html_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> AuthUser:
    """HTML cabinet pages: session user or redirect to /login/?next=…"""
    from app.auth.session import get_current_user_async
    from app.utils.safe_redirect import login_url_with_next

    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(
            status_code=302,
            headers={"Location": login_url_with_next(request.url.path)},
        )
    return user


async def require_user_api_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> AuthUser:
    """JSON/API cabinet routes for site + Mini App (cookie or Bearer)."""
    user = await resolve_request_user_async(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


def get_consultant(db: Session, user: AuthUser) -> Consultant:
    consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
    if not consultant:
        # Phase 5: soft gate - offer become-specialist instead of bouncing to landing
        raise HTTPException(status_code=302, headers={"Location": "/become-specialist/"})
    return consultant


async def get_consultant_async(db, user: AuthUser) -> Consultant:
    from sqlalchemy import select

    consultant = (await db.execute(select(Consultant).where(Consultant.user_id == user.id))).scalar_one_or_none()
    if not consultant:
        raise HTTPException(status_code=302, headers={"Location": "/become-specialist/"})
    return consultant


def require_specialist_mode(request: Request, db: Session, user: AuthUser) -> Consultant:
    """Specialist cabinet routes: need Consultant profile."""
    from app.services.active_mode import MODE_SPECIALIST, set_active_mode

    consultant = get_consultant(db, user)
    set_active_mode(request, MODE_SPECIALIST, has_consultant=True)
    return consultant


async def require_specialist_mode_async(request: Request, db, user: AuthUser) -> Consultant:
    from app.services.active_mode import MODE_SPECIALIST, set_active_mode

    consultant = await get_consultant_async(db, user)
    set_active_mode(request, MODE_SPECIALIST, has_consultant=True)
    return consultant


def _platform_admin_allowed(user: AuthUser) -> bool:
    """Staff/superuser, and when OWNER allowlist is set - only those identities."""
    from app.config import get_settings

    if not user.is_platform_admin:
        return False
    owners = get_settings().platform_admin_owners()
    if not owners:
        return False
    email = (user.email or "").strip().lower()
    username = (user.username or "").strip().lower()
    return email in owners or username in owners


def require_platform_admin(request: Request, db: Session) -> AuthUser:
    """Admin A0 gate: feature flag + owner allowlist + is_staff/is_superuser."""
    from app.config import get_settings

    settings = get_settings()
    if not settings.platform_admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login/?next=/platform-admin/"})
    if not _platform_admin_allowed(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


async def require_platform_admin_async(request: Request, db) -> AuthUser:
    """AsyncSession variant of require_platform_admin."""
    from app.auth.session import get_current_user_async
    from app.config import get_settings

    settings = get_settings()
    if not settings.platform_admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    user = await get_current_user_async(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login/?next=/platform-admin/"})
    if not _platform_admin_allowed(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def find_consultant(db: Session, user: AuthUser | None) -> Consultant | None:
    if not user:
        return None
    return db.query(Consultant).filter(Consultant.user_id == user.id).first()


def normalize_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value or value.lower() in ("none", "null"):
        return None
    if value.startswith(("http://", "https://")):
        # Guard against stored "https://None"
        host = value.split("://", 1)[-1].strip().lower()
        if not host or host in ("none", "null"):
            return None
        return value
    # Telegram @username → t.me link
    if value.startswith("@") and " " not in value:
        return f"https://t.me/{value.lstrip('@')}"
    return f"https://{value.lstrip('/')}"


def blank_field(value: str | None) -> str:
    """Hide empty DB values and literal 'None' strings in form fields."""
    text = (value or "").strip()
    if not text or text.lower() in ("none", "null"):
        return ""
    lowered = text.lower()
    if lowered in ("http://none", "https://none", "http://null", "https://null"):
        return ""
    return text


def normalize_phone(phone: str | None) -> str:
    """Normalize RU mobile to +7XXXXXXXXXX (fits consultants.phone max 15).

    Accepts masks like +7 (999) 123-45-67, 8XXXXXXXXXX, 9XXXXXXXXX.
    Returns empty string if incomplete or not a Russian mobile number.
    """
    raw = (phone or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("8") and len(digits) >= 11:
        digits = "7" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    if len(digits) > 11 and digits.startswith("7"):
        digits = digits[:11]
    if len(digits) == 11 and digits.startswith("7") and digits[1] == "9":
        return f"+{digits}"
    return ""
