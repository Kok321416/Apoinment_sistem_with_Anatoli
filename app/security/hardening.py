"""HTTP hardening middleware — rate limits + extra headers without changing UX."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.security.request_guards import (
    client_ip,
    is_auth_abuse_path,
    is_public_booking_write,
    should_skip_rate_limit,
)
from app.services.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

# Generous global cap: normal browsing / SPA-like page loads stay fine.
# Shared NAT may share an IP — keep headroom high.
_GLOBAL_MAX = 240
_GLOBAL_WINDOW = 60

# Auth POSTs / API auth: stop stuffing without locking out real users.
_AUTH_MAX = 30
_AUTH_WINDOW = 300

# Public booking POST: prevent spam bookings / form floods.
_BOOK_MAX = 40
_BOOK_WINDOW = 300


class AbuseProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if should_skip_rate_limit(path):
            return await call_next(request)

        ip = client_ip(request)

        if is_auth_abuse_path(path, method):
            if not check_rate_limit(f"auth:{ip}", max_calls=_AUTH_MAX, window_sec=_AUTH_WINDOW):
                return _too_many(request, "Слишком много попыток. Подождите несколько минут.")

        if is_public_booking_write(path, method):
            if not check_rate_limit(f"book:{ip}", max_calls=_BOOK_MAX, window_sec=_BOOK_WINDOW):
                return _too_many(request, "Слишком много запросов записи. Попробуйте позже.")

        if not check_rate_limit(f"global:{ip}", max_calls=_GLOBAL_MAX, window_sec=_GLOBAL_WINDOW):
            logger.warning("global rate limit hit ip=%s path=%s", ip, path)
            return _too_many(request, "Слишком много запросов. Подождите немного.")

        return await call_next(request)


def _too_many(request: Request, message: str):
    accept = (request.headers.get("accept") or "").lower()
    wants_json = "application/json" in accept or request.url.path.startswith("/api/")
    headers = {"Retry-After": "60"}
    if wants_json:
        return JSONResponse({"error": message}, status_code=429, headers=headers)
    return PlainTextResponse(message, status_code=429, headers=headers)
