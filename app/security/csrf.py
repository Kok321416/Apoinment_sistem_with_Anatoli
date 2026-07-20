"""CSRF token helpers for HTML forms."""
import secrets

from fastapi import Request


def ensure_csrf_token(request: Request) -> str:
    if "session" not in request.scope:
        return ""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf_token(request: Request, form_token: str | None) -> bool:
    if "session" not in request.scope:
        return False
    expected = request.session.get("csrf_token")
    if not expected or not form_token:
        return False
    return secrets.compare_digest(expected, form_token)
