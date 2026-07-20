from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models import Consultant, EmailAddress, SocialAccount, User

settings = get_settings()

URL_MAP = {
    "home": "/",
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
    "google_calendar_connect": "/integrations/google/connect/",
    "google_calendar_callback": "/integrations/google/callback/",
    "connect_telegram_app": "/integrations/telegram/connect-app/",
}


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


def build_header_context(db, user) -> dict:
    if not user:
        return {"header_consultant_name": "", "header_account_display": ""}
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
    if social:
        if social.provider == "google" and user.email:
            account = account or user.email
        elif social.provider == "telegram":
            account = account or user.username

    return {"header_consultant_name": name, "header_account_display": account or user.username}


def page_context(request, db, user=None, **extra):
    ctx = {
        "request": request,
        "user": user,
        "telegram_bot_username": settings.telegram_bot_username,
        "show_telegram_welcome": request.session.pop("show_telegram_welcome", False),
        "url_for": url_for,
        **build_header_context(db, user),
        **extra,
    }
    return ctx
