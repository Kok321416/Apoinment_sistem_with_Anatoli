import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.database import engine
from app.routers import (
    api,
    calendar_schedule,
    diagnostics,
    oauth,
    pages,
    platform_admin,
    profile_api,
    public_specialist,
    services_api,
    specialist_booking,
    telegram_webhook,
)
from app.security.hardening import AbuseProtectionMiddleware

settings = get_settings()
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Appointment System",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

_session_same_site = settings.session_same_site if settings.session_same_site in ("lax", "strict", "none") else "lax"
# SameSite=None requires Secure; needed for Telegram Mini App WebView cookies.
_https_only = settings.site_url.startswith("https://") or _session_same_site == "none"

# add_middleware: last added = outermost on the request path.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    https_only=_https_only,
    same_site=_session_same_site,
)
app.add_middleware(AbuseProtectionMiddleware)
if not settings.debug and settings.allowed_hosts:
    # Protect Host-header attacks in production; keep localhost for health probes.
    _hosts = list(dict.fromkeys([*settings.allowed_hosts, "localhost", "127.0.0.1"]))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

settings.media_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")

app.include_router(pages.router)
app.include_router(diagnostics.router)
app.include_router(calendar_schedule.router)
app.include_router(services_api.router)
app.include_router(profile_api.router)
app.include_router(public_specialist.router)
app.include_router(api.router)
app.include_router(specialist_booking.router)
app.include_router(oauth.router)
app.include_router(platform_admin.router)
app.include_router(telegram_webhook.router)


@app.get("/health")
async def health():
    """Liveness: no MySQL. Telegram keepalive and load balancers must stay fast."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    from app.db_schema import get_schema_health
    from app.services.perf_metrics import snapshot as perf_snapshot
    from app.services.redis_client import redis_health

    schema = get_schema_health()
    redis = redis_health()
    status = "degraded" if schema.get("degraded") else "ok"
    payload = {
        "status": status,
        "schema": schema,
        "redis": redis,
        "perf": perf_snapshot(top_n=5),
    }
    try:
        from app.services.ops_alerts import notify_health_if_bad

        notify_health_if_bad(payload)
    except Exception:
        logger.exception("ops health alert failed")
    if schema.get("degraded"):
        from fastapi.responses import JSONResponse

        return JSONResponse(payload, status_code=503)
    return payload


@app.get("/health/mini-app")
async def health_mini_app():
    """Public checklist for Telegram Mini App (DNS/HTTPS/assets/session)."""
    from pathlib import Path

    sdk = Path(settings.static_dir) / "js" / "vendor" / "telegram-web-app.js"
    boot = Path(settings.static_dir) / "js" / "telegram-webapp.js"
    issues: list[str] = []
    if not sdk.is_file():
        issues.append("missing_static_vendor_telegram_web_app_js")
    if not boot.is_file():
        issues.append("missing_static_telegram_webapp_boot_js")
    if settings.session_same_site != "none" and settings.site_url.startswith("https://"):
        issues.append("session_same_site_should_be_none_for_telegram_webview")
    if not settings.telegram_bot_token:
        issues.append("telegram_bot_token_not_set")
    return {
        "status": "ok" if not issues else "degraded",
        "site_url": settings.site_url.rstrip("/"),
        "session_same_site": settings.session_same_site,
        "telegram_bot_username": settings.telegram_bot_username or None,
        "webhook_configured": bool(settings.telegram_webhook_secret),
        "assets": {
            "vendor_sdk_bytes": sdk.stat().st_size if sdk.is_file() else 0,
            "boot_js_bytes": boot.stat().st_size if boot.is_file() else 0,
        },
        "issues": issues,
        "dns_hint": "AAAA for allyourclients.ru must be absent; only A -> 31.31.197.47",
        "endpoints": {
            "hub": "/tg/",
            "webapp_auth": "/api/telegram/webapp-auth",
            "auth_telegram": "/api/auth/telegram",
            "hub_state": "/api/telegram/hub-state",
            "me": "/api/me",
        },
    }


@app.get("/sw.js")
async def service_worker():
    """Root-scoped SW so PWA can cache /static/* without caching HTML/API."""
    from fastapi.responses import FileResponse

    path = Path(settings.static_dir) / "sw.js"
    return FileResponse(
        path,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache",
        },
    )


def _internal_secret_ok(request: Request) -> bool:
    import secrets as _secrets

    expected = (settings.cron_secret or settings.bot_api_secret or "").strip()
    if not expected:
        return False
    got = (
        (request.headers.get("x-cron-secret") or "").strip()
        or (request.headers.get("x-bot-api-secret") or "").strip()
        or (request.query_params.get("token") or "").strip()
    )
    return bool(got) and _secrets.compare_digest(got, expected)


@app.get("/internal/cron/reminders/")
@app.post("/internal/cron/reminders/")
async def cron_send_reminders(request: Request):
    """Run booking reminders. Auth: CRON_SECRET or BOT_API_SECRET via header/query."""
    from fastapi.responses import JSONResponse

    if not (settings.cron_secret or settings.bot_api_secret or "").strip():
        return JSONResponse({"ok": False, "error": "cron secret not configured"}, status_code=503)
    if not _internal_secret_ok(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        from app.services.telegram import send_reminders_async

        sent = await send_reminders_async()
        return {"ok": True, "sent": sent}
    except Exception as exc:
        logger.exception("cron reminders failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/internal/metrics/")
async def internal_metrics(request: Request):
    """Process request latency snapshot. Auth: CRON_SECRET or BOT_API_SECRET."""
    from fastapi.responses import JSONResponse

    from app.services.perf_metrics import snapshot as perf_snapshot

    if not _internal_secret_ok(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return {"ok": True, "perf": perf_snapshot(top_n=25)}


@app.get("/internal/explain/")
async def internal_explain(request: Request):
    """EXPLAIN hot queries (Phase E acceptance). Auth: CRON_SECRET or BOT_API_SECRET."""
    from fastapi.responses import JSONResponse

    from app.database import SessionLocal
    from app.services.query_explain import explain_hot_queries, list_expected_indexes

    if not _internal_secret_ok(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    db = SessionLocal()
    try:
        return {
            "ok": True,
            "expected_indexes": list_expected_indexes(),
            "explain": explain_hot_queries(db),
        }
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    from app.db_schema import ensure_all_schema

    try:
        ensure_all_schema()
    except Exception:
        logger.exception("ensure_all_schema failed on startup")
    try:
        from app.db_schema import ensure_diagnostics_schema
        from app.services.diagnostics_service import _mark_diagnostics_ddl_ready

        if ensure_diagnostics_schema():
            _mark_diagnostics_ddl_ready()
            logger.info("Diagnostics tables ready")
        else:
            logger.error(
                "Diagnostics tables are missing — run ensure_diagnostics_schema on deploy; "
                "hub will open but saves may fail until tables exist"
            )
    except Exception:
        logger.exception("diagnostics ddl ready flag init failed")
    if not settings.debug:
        if settings.secret_key in ("", "change-me-in-production"):
            logger.critical("SECRET_KEY is weak or default — set a long random value in production")
        if not settings.bot_api_secret:
            logger.warning("BOT_API_SECRET is not set — bot API uses TELEGRAM_BOT_TOKEN header only")
    if settings.telegram_webhook_secret and settings.telegram_bot_token:
        try:
            from bot.aiogram_app import get_bot, setup_bot_meta, verify_bot_identity
            from bot.webhook_setup import install_webhook

            bot = get_bot()
            await verify_bot_identity(bot)
            await setup_bot_meta(bot)
            ok = await install_webhook(bot)
            if ok:
                logger.info("Telegram webhook mode active (disable separate bot.run / systemd polling)")
        except Exception:
            logger.exception("Telegram webhook setup failed on startup")
    logger.info("FastAPI app started. SITE_URL=%s", settings.site_url)


from app.db_schema import bootstrap_on_import

bootstrap_on_import()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    import uuid

    rid = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex[:16]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.middleware("http")
async def perf_timing_middleware(request: Request, call_next):
    import time

    from app.services.perf_metrics import record_request

    path = request.url.path
    if path.startswith("/static/") or path.startswith("/media/"):
        return await call_next(request)
    t0 = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - t0) * 1000.0
    slow_ms = float(getattr(settings, "perf_slow_ms", 500) or 500)
    try:
        record_request(
            path=path,
            status_code=int(getattr(response, "status_code", 200) or 200),
            duration_ms=duration_ms,
            slow_ms=slow_ms,
        )
    except Exception:
        logger.exception("perf_timing record failed")
    if getattr(settings, "perf_timing_header", True):
        response.headers["X-Process-Time"] = f"{duration_ms:.1f}ms"
    _watch = (
        "/tg/",
        "/health",
        "/health/ready",
        "/api/auth/telegram",
        "/api/telegram/webapp-auth",
        "/api/telegram/hub-state",
    )
    if path in _watch:
        rid = getattr(request.state, "request_id", "-")
        logger.info(
            "request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
            rid,
            request.method,
            path,
            getattr(response, "status_code", "?"),
            duration_ms,
        )
    if slow_ms > 0 and duration_ms >= slow_ms:
        logger.warning(
            "slow_request path=%s status=%s duration_ms=%.1f",
            path,
            getattr(response, "status_code", "?"),
            duration_ms,
        )
    return response


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
    response.headers.setdefault("X-DNS-Prefetch-Control", "off")
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
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
    )
    # Do not cache HTML authenticated shells by default (static/media set their own).
    path = request.url.path
    if not path.startswith("/static/") and not path.startswith("/media/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.site_url.startswith("https://"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def platform_error_capture_middleware(request: Request, call_next):
    """Persist unexpected exceptions / 5xx and ping ops Telegram."""
    from fastapi import HTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException

    path = request.url.path
    skip = path.startswith("/static/") or path.startswith("/media/")

    try:
        response = await call_next(request)
    except (HTTPException, StarletteHTTPException) as http_exc:
        if not skip and getattr(http_exc, "status_code", 0) >= 500:
            try:
                from app.auth.session import get_session_user_id
                from app.services.ops_alerts import notify_ops_alert
                from app.services.platform_errors import record_platform_error

                uid = get_session_user_id(request) if "session" in request.scope else None
                detail = getattr(http_exc, "detail", None)
                record_platform_error(
                    path=path,
                    method=request.method,
                    status_code=http_exc.status_code,
                    message=str(detail or http_exc)[:512],
                    user_id=uid,
                    ip=request.client.host if request.client else None,
                )
                notify_ops_alert(
                    kind="http_5xx",
                    status_code=http_exc.status_code,
                    message=str(detail or http_exc)[:512],
                    request=request,
                    user_id=uid,
                )
            except Exception:
                logger.exception("platform_error_capture http 5xx failed")
        raise
    except Exception as exc:
        try:
            from app.auth.session import get_session_user_id
            from app.services.platform_errors import record_exception

            uid = None
            if "session" in request.scope:
                uid = get_session_user_id(request)
            record_exception(request, exc, user_id=uid)
        except Exception:
            logger.exception("platform_error_capture failed")
        raise

    if skip or response.status_code < 500:
        return response
    try:
        from app.auth.session import get_session_user_id
        from app.services.ops_alerts import notify_ops_alert
        from app.services.platform_errors import record_platform_error

        uid = get_session_user_id(request) if "session" in request.scope else None
        record_platform_error(
            path=path,
            method=request.method,
            status_code=response.status_code,
            message=f"HTTP {response.status_code}",
            user_id=uid,
            ip=request.client.host if request.client else None,
        )
        notify_ops_alert(
            kind="http_5xx",
            status_code=response.status_code,
            message=f"HTTP {response.status_code}",
            request=request,
            user_id=uid,
        )
    except Exception:
        logger.exception("platform_error_capture 5xx response failed")
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
        "/s/",
        "/tg/",
        "/my-bookings/",
        "/platform-admin/",
        "/telegram/webhook/",
        "/health",
    )
    path = request.url.path
    if any(path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)
    if "session" not in request.scope:
        return await call_next(request)
    if not get_session_user_id(request):
        return await call_next(request)
    # Fast path: most users already have a password (flag set at login).
    if request.session.get("has_usable_password"):
        return await call_next(request)
    db = None
    try:
        db = SessionLocal()
        user = get_current_user(request, db)
        if user and user.has_usable_password:
            request.session["has_usable_password"] = True
        elif user and not user.has_usable_password and not path.startswith("/accounts/"):
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
