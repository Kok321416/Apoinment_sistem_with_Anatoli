from datetime import date, datetime, time
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from app.branding import auth_provider_label, booking_status_label
from app.config import get_settings
from app.content.landing_copy import (
    CTA_BLOCK,
    FEATURES,
    GUIDE,
    GUIDE_META,
    HERO,
    HOW_IT_WORKS,
    LANDING_META,
    STATS_LABELS,
    faq_with_support,
    footer_with_context,
)
from app.security.csrf import ensure_csrf_token
from app.models import Consultant, EmailAddress, SocialAccount, User
from app.services.landing_stats import landing_stats

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
templates.env.filters["media_url"] = media_url
templates.env.filters["date"] = django_date
templates.env.filters["time"] = django_time
templates.env.filters["truncatewords"] = truncatewords
templates.env.filters["urlencode"] = lambda value: quote(str(value or ""), safe="/")
templates.env.filters["auth_provider"] = auth_provider_label


def build_header_context(db, user) -> dict:
    if not user:
        return {"header_consultant_name": "", "header_account_display": ""}
    try:
        name = ""
        consultant = db.query(Consultant).filter(Consultant.user_id == user.id).first()
        if consultant:
            parts = [consultant.first_name or "", consultant.last_name or ""]
            name = " ".join(p for p in parts if p).strip() or consultant.email or user.username
        else:
            db_user = db.get(User, user.id)
            name = (db_user.get_full_name() if db_user else "") or user.username

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
        if not account and "@" in user.username:
            account = user.username

        social = db.query(SocialAccount).filter(SocialAccount.user_id == user.id).first()
        if social and social.provider == "telegram":
            account = account or user.username

        return {"header_consultant_name": name, "header_account_display": account or user.username}
    except Exception:
        return {"header_consultant_name": user.username, "header_account_display": user.username or ""}


def _session_pop(request, key: str, default=False):
    if "session" not in request.scope:
        return default
    return request.session.pop(key, default)


def page_context(request, db, user=None, **extra):
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
        "admin_telegram_username": settings.admin_telegram_username,
        **build_header_context(db, user),
        **extra,
    }
    return ctx


def landing_context(request, db, user=None, **extra):
    year = datetime.now().year
    ctx = page_context(request, db, user, **extra)
    ctx.update(
        {
            "landing_meta": LANDING_META,
            "hero": HERO,
            "stats_labels": STATS_LABELS,
            "stats": landing_stats(db),
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
