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

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    https_only=settings.site_url.startswith("https://"),
)

settings.media_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(oauth.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    logger.info("FastAPI app started. SITE_URL=%s", settings.site_url)


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
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user and not user.has_usable_password and not path.startswith("/accounts/"):
            next_url = path
            if request.url.query:
                next_url += f"?{request.url.query}"
            from fastapi.responses import RedirectResponse
            redirect = f"/accounts/password/set/?{__import__('urllib').parse.urlencode({'next': next_url})}"
            return RedirectResponse(redirect, status_code=302)
    finally:
        db.close()
    return await call_next(request)
