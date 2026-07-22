import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import engine
from app.routers import api, calendar_schedule, oauth, pages, profile_api, public_specialist, services_api

settings = get_settings()
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Appointment System", docs_url="/api/docs" if settings.debug else None)

_session_same_site = settings.session_same_site if settings.session_same_site in ("lax", "strict", "none") else "lax"
# SameSite=None requires Secure; needed for Telegram Mini App WebView cookies.
_https_only = settings.site_url.startswith("https://") or _session_same_site == "none"

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    https_only=_https_only,
    same_site=_session_same_site,
)

settings.media_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")

app.include_router(pages.router)
app.include_router(calendar_schedule.router)
app.include_router(services_api.router)
app.include_router(profile_api.router)
app.include_router(public_specialist.router)
app.include_router(api.router)
app.include_router(oauth.router)


@app.get("/health")
async def health():
    from app.db_schema import get_schema_health

    schema = get_schema_health()
    status = "degraded" if schema.get("degraded") else "ok"
    return {"status": status, "schema": schema}


@app.on_event("startup")
def startup():
    from app.db_schema import ensure_all_schema

    try:
        ensure_all_schema()
    except Exception:
        logger.exception("ensure_all_schema failed on startup")
    if not settings.debug:
        if settings.secret_key in ("", "change-me-in-production"):
            logger.critical("SECRET_KEY is weak or default — set a long random value in production")
        if not settings.bot_api_secret:
            logger.warning("BOT_API_SECRET is not set — bot API uses TELEGRAM_BOT_TOKEN header only")
    logger.info("FastAPI app started. SITE_URL=%s", settings.site_url)


from app.db_schema import bootstrap_on_import

bootstrap_on_import()


@app.middleware("http")
async def static_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        # Versioned assets (?v=) can be cached long-term; unversioned get 1 day.
        if request.url.query and "v=" in request.url.query:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
    elif path.startswith("/media/"):
        response.headers.setdefault("Cache-Control", "public, max-age=604800")
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # Telegram Mini App opens the site inside Telegram WebView / iframe.
    # DENY would break the in-Telegram web app; allow only Telegram origins.
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]
    csp = response.headers.get("content-security-policy", "")
    frame_ancestors = (
        "frame-ancestors 'self' https://web.telegram.org https://telegram.org "
        "https://*.telegram.org"
    )
    if "frame-ancestors" not in csp:
        response.headers["Content-Security-Policy"] = (
            f"{csp}; {frame_ancestors}".strip("; ").strip() if csp else frame_ancestors
        )
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.site_url.startswith("https://"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def password_required_middleware(request: Request, call_next):
    from app.auth.session import get_current_user, get_session_user_id
    from app.database import SessionLocal

    exempt_prefixes = (
        "/accounts/password/set",
        "/accounts/logout",
        "/accounts/confirm-email/",
        "/accounts/telegram/",
        "/accounts/yandex/",
        "/static/",
        "/media/",
        "/api/",
        "/book/",
        "/tg/",
        "/my-bookings/",
        "/health",
    )
    path = request.url.path
    if any(path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)
    if "session" not in request.scope:
        return await call_next(request)
    if not get_session_user_id(request):
        return await call_next(request)
    db = None
    try:
        db = SessionLocal()
        user = get_current_user(request, db)
        if user and not user.has_usable_password and not path.startswith("/accounts/"):
            next_url = path
            if request.url.query:
                next_url += f"?{request.url.query}"
            from fastapi.responses import RedirectResponse
            redirect = f"/accounts/password/set/?{__import__('urllib').parse.urlencode({'next': next_url})}"
            return RedirectResponse(redirect, status_code=302)
    except Exception:
        logger.exception("password_required_middleware failed for %s", path)
    finally:
        if db is not None:
            db.close()
    return await call_next(request)
