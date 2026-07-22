from datetime import date, datetime, time
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from app.branding import auth_provider_label, booking_status_label
from app.config import get_settings
from app.deps import blank_field
from app.services.yandex_auth import yandex_oauth_configured
from app.content.landing_copy import (
    CTA_BLOCK,
    FEATURES,
    GUIDE,
    GUIDE_META,
    HERO,
    HOW_IT_WORKS,
    LANDING_META,
    VALUE_POINTS,
    faq_with_support,
    footer_with_context,
)
from app.security.csrf import ensure_csrf_token
from app.models import Consultant, EmailAddress, User

settings = get_settings()

URL_MAP = {
    "home": "/",
    "landing": "/",
    "dashboard": "/dashboard/",
    "guide": "/guide/",
    "privacy": "/privacy/",
    "terms": "/terms/",
    "register": "/register/",
    "login": "/login/",
    "logout": "/logout/",
    "calendars": "/calendars/",
    "services": "/services/",
    "booking": "/booking/",
    "profile": "/profile/",
    "integrations": "/integrations/",
    "client_cards_list": "/clients/",
    "booking_redirect": "/book/",
    "account_login": "/accounts/login/",
    "account_set_password": "/accounts/password/set/",
    "account_reset_password": "/accounts/password/reset/",
    "connect_telegram_app": "/integrations/telegram/connect-app/",
    "account_email": "/profile/",
    "socialaccount_connections": "/accounts/social/connections/",
}


def media_url(path: str | None) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://") or path.startswith("/"):
        return path
    return f"/media/{path.lstrip('/')}"


def media_relative_path(stored: str | None) -> str:
    if not stored:
        return ""
    path = stored.lstrip("/")
    if path.startswith("media/"):
        path = path[6:]
    return path


def media_file_version(stored: str | None) -> int:
    rel = media_relative_path(stored)
    if not rel:
        return 0
    path = settings.media_root / rel
    if path.is_file():
        return int(path.stat().st_mtime)
    return 0


def profile_photo_src(path: str | None) -> str:
    url = media_url(path)
    if not url:
        return ""
    version = media_file_version(path)
    return f"{url}?v={version}" if version else url


def cut_filter(value: str | None, chars: str) -> str:
    return (value or "").replace(chars, "")


def _format_value(value, fmt: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        for parser in (
            lambda v: datetime.fromisoformat(v),
            lambda v: datetime.strptime(v, "%H:%M:%S").time(),
            lambda v: datetime.strptime(v, "%H:%M").time(),
            lambda v: datetime.strptime(v, "%Y-%m-%d").date(),
        ):
            try:
                value = parser(value)
                break
            except ValueError:
                continue
        else:
            return value
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    if isinstance(value, time):
        return value.strftime(fmt)
    return str(value)


def django_date(value, fmt: str = "d.m.Y") -> str:
    mapping = {"d.m.Y": "%d.%m.%Y"}
    return _format_value(value, mapping.get(fmt, fmt))


def django_time(value, fmt: str = "H:i") -> str:
    mapping = {"H:i": "%H:%M"}
    return _format_value(value, mapping.get(fmt, fmt))


def truncatewords(value: str | None, count: int = 12) -> str:
    words = (value or "").split()
    if len(words) <= count:
        return value or ""
    return " ".join(words[:count]) + "..."


def url_for(name: str, *args, **kwargs) -> str:
    if name == "calendar_detail":
        return f"/calendars/{args[0] if args else kwargs.get('calendar_id', '')}/"
    if name == "calendar_settings_edit":
        cid = args[0] if args else kwargs.get("calendar_id", "")
        return f"/calendars/{cid}/settings/"
    if name == "public_booking":
        cid = args[0] if args else kwargs.get("calendar_id", "")
        return f"/book/{cid}/"
    if name == "client_card_detail":
        return f"/clients/{args[0] if args else kwargs.get('card_id', '')}/"
    if name == "confirm_booking_telegram_browser":
        return f"/book/confirm-telegram/{args[0] if args else kwargs.get('link_token', '')}/"
    return URL_MAP.get(name, "/")


templates = Jinja2Templates(directory=str(settings.templates_dir))
templates.env.filters["cut"] = cut_filter
templates.env.filters["blank_field"] = blank_field
templates.env.filters["media_url"] = media_url
templates.env.filters["profile_photo_src"] = profile_photo_src
templates.env.filters["date"] = django_date
templates.env.filters["time"] = django_time
templates.env.filters["truncatewords"] = truncatewords
templates.env.filters["urlencode"] = lambda value: quote(str(value or ""), safe="/")
templates.env.filters["auth_provider"] = auth_provider_label
templates.env.filters["booking_status"] = booking_status_label


def build_header_context(db, user) -> dict:
    if not user or db is None:
        return {"header_consultant_name": "", "header_account_display": ""}
    try:
        name = ""
        consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
        if consultant:
            parts = [
                consultant.first_name or "",
                consultant.middle_name or "",
                consultant.last_name or "",
            ]
            name = " ".join(p for p in parts if p).strip()
        if not name:
            db_user = db.get(User, user.id)
            if db_user:
                name = f"{db_user.first_name or ''} {db_user.last_name or ''}".strip()
        if not name and hasattr(user, "get_full_name"):
            name = (user.get_full_name() or "").strip()

        account = ""
        primary = (
            db.query(EmailAddress)
            .filter(EmailAddress.user_id == user.id, EmailAddress.primary.is_(True))
            .first()
        )
        if primary and primary.email:
            account = primary.email
        if not account and user.email:
            account = user.email
        if not account and "@" in (user.username or ""):
            account = user.username
        if not account and consultant and consultant.email:
            account = consultant.email

        top = account or user.username or ""
        bottom = name
        if bottom and bottom.lower() == top.lower():
            bottom = ""
        if not bottom:
            bottom = "Специалист"

        return {
            "header_consultant_name": bottom,
            "header_account_display": top,
        }
    except Exception:
        return {
            "header_consultant_name": "Специалист",
            "header_account_display": getattr(user, "username", "") or "",
        }


def _session_pop(request, key: str, default=False):
    if "session" not in request.scope:
        return default
    return request.session.pop(key, default)


def page_context(request, db, user=None, **extra):
    from app.services.active_mode import get_active_mode, user_has_consultant

    has_consultant = False
    active_mode = "client"
    if user is not None and db is not None:
        has_consultant = user_has_consultant(db, user.id)
        active_mode = get_active_mode(request, db, user.id)
    ctx = {
        "request": request,
        "user": user,
        "csrf_token": ensure_csrf_token(request),
        "telegram_bot_username": settings.telegram_bot_username,
        "show_telegram_welcome": _session_pop(request, "show_telegram_welcome", False),
        "url_for": url_for,
        "site_brand_name": settings.site_brand_name,
        "site_url": settings.site_url.rstrip("/"),
        "canonical_url": str(request.url).split("?")[0],
        "support_email": settings.support_email,
        "yandex_metrika_id": settings.yandex_metrika_id,
        "yandex_oauth_enabled": yandex_oauth_configured(),
        "admin_telegram_username": settings.admin_telegram_username,
        "has_consultant": has_consultant,
        "active_mode": active_mode,
        "show_mode_switcher": bool(user and has_consultant),
        "impersonator_id": None,
        "load_telegram_webapp": False,
        **build_header_context(db, user),
        **extra,
    }
    if "session" in getattr(request, "scope", {}):
        from app.auth.session import get_impersonator_id

        ctx["impersonator_id"] = get_impersonator_id(request)
    return ctx


def landing_context(request, db, user=None, **extra):
    year = datetime.now().year
    ctx = page_context(request, db, user, **extra)
    ctx.update(
        {
            "landing_meta": LANDING_META,
            "hero": HERO,
            "value_points": VALUE_POINTS,
            "features": FEATURES,
            "how_it_works": HOW_IT_WORKS,
            "cta_block": CTA_BLOCK,
            "faq_items": faq_with_support(settings.support_email),
            "footer_copy": footer_with_context(settings.support_email, settings.site_brand_name, year),
        }
    )
    return ctx


def guide_context(request, db, user=None, **extra):
    ctx = landing_context(request, db, user, **extra)
    ctx.update({"guide_meta": GUIDE_META, "guide": GUIDE})
    return ctx
