"""Safe internal redirect targets after login."""

from urllib.parse import urlencode, urlparse

DEFAULT_AFTER_LOGIN = "/dashboard/"


def safe_next_url(raw: str | None, default: str = DEFAULT_AFTER_LOGIN) -> str:
    if not raw:
        return default
    value = raw.strip()
    if not value.startswith("/") or value.startswith("//"):
        return default
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return default
    return value or default


def login_url_with_next(next_path: str | None) -> str:
    safe = safe_next_url(next_path, default="")
    if not safe:
        return "/login/"
    return f"/login/?{urlencode({'next': safe})}"


def signup_error_redirect(next_url: str | None, error: str) -> str:
    """On OAuth/register failure, return to specialist welcome when next is /s/{slug}/..."""
    safe = safe_next_url(next_url, default="")
    if safe.startswith("/s/"):
        parts = [p for p in safe.split("/") if p]
        if len(parts) >= 2 and parts[0] == "s":
            slug = parts[1]
            profile = f"/s/{slug}/"
            return f"/s/{slug}/welcome/?{urlencode({'error': error, 'next': profile})}"
    return f"/register/?error={error}"
