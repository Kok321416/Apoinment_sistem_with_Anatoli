import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import api, oauth, pages

settings = get_settings()
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Appointment System", docs_url="/api/docs" if settings.debug else None)

_session_same_site = settings.session_same_site if settings.session_same_site in ("lax", "strict", "none") else "lax"

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    https_only=settings.site_url.startswith("https://"),
    same_site=_session_same_site,
)

settings.media_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(oauth.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
def startup():
    from app.db_schema import ensure_telegram_login_schema

    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logger.exception("create_all failed on startup")
    try:
        ensure_telegram_login_schema()
    except Exception:
        logger.exception("ensure_telegram_login_schema failed on startup")
    if not settings.debug:
        if settings.secret_key in ("", "change-me-in-production"):
            logger.critical("SECRET_KEY is weak or default — set a long random value in production")
        if not settings.bot_api_secret:
            logger.warning("BOT_API_SECRET is not set — bot API uses TELEGRAM_BOT_TOKEN header only")
    logger.info("FastAPI app started. SITE_URL=%s", settings.site_url)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.site_url.startswith("https://"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def password_required_middleware(request: Request, call_next):
    from app.auth.session import get_current_user
    from app.database import SessionLocal

    exempt_prefixes = (
        "/accounts/password/set",
        "/accounts/logout",
        "/accounts/confirm-email/",
        "/accounts/telegram/",
        "/static/",
        "/media/",
        "/api/",
        "/book/",
    )
    path = request.url.path
    if any(path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)
    if "session" not in request.scope:
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
