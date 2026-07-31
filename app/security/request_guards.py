"""Request IP and abuse-path helpers (Security agent)."""
from __future__ import annotations

from fastapi import Request

# Paths that must never be rate-limited heavily (CDN-like / health).
_SKIP_PREFIXES = (
    "/static/",
    "/media/",
    "/health",
    "/internal/cron/",
    "/favicon.ico",
)

# Sensitive auth / signup / reset — stricter buckets.
_AUTH_PREFIXES = (
    "/login/",
    "/register/",
    "/accounts/password/",
    "/accounts/verify-email/",
    "/api/auth/",
    "/accounts/telegram/",
    "/accounts/yandex/",
    "/accounts/vk/",
)

# Public booking writes / slot polling can be abused for scrape + spam.
_PUBLIC_WRITE_MARKERS = (
    "/s/",
)


def client_ip(request: Request) -> str:
    """Best-effort client IP. Prefer first X-Forwarded-For hop (nginx)."""
    fwd = (request.headers.get("x-forwarded-for") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()[:64] or "0.0.0.0"
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "0.0.0.0"


def should_skip_rate_limit(path: str) -> bool:
    return any(path.startswith(p) for p in _SKIP_PREFIXES)


def is_auth_abuse_path(path: str, method: str) -> bool:
    if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
        # GET on login is fine; still soft-limit via global.
        if path.startswith("/api/auth/"):
            return True
        return False
    return any(path.startswith(p) for p in _AUTH_PREFIXES)


def is_public_booking_write(path: str, method: str) -> bool:
    if method.upper() != "POST":
        return False
    if not path.startswith("/s/"):
        return False
    # Slots JSON is GET; book form is POST on /s/.../c/.../
    return "/c/" in path or path.rstrip("/").endswith("/welcome")
