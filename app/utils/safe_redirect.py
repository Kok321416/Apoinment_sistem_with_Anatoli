"""Safe internal redirect targets after login."""

from urllib.parse import urlparse

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
    from urllib.parse import urlencode

    return f"/login/?{urlencode({'next': safe})}"
