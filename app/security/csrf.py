"""CSRF token helpers + optional HTML-form middleware (Phase 3).

JSON /api/* routes keep per-handler validate_csrf_token + X-CSRF-Token.
This middleware only covers browser HTML form POSTs (urlencoded / multipart).

Modes (CSRF_HTML_MODE):
  off     — disabled
  log     — dry-run: log missing/invalid tokens, never block (default)
  enforce — reject with 403
"""
from __future__ import annotations

import logging
import re
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_FORM_CT = ("application/x-www-form-urlencoded", "multipart/form-data")
_EXEMPT_PREFIXES = (
    "/api/",
    "/telegram/webhook/",
    "/internal/",
    "/static/",
    "/media/",
    "/health",
)
_MULTIPART_TOKEN_RE = re.compile(
    rb'Content-Disposition:\s*form-data;\s*name="(?:csrf_token|csrfmiddlewaretoken)"'
    rb"(?:;[^\r\n]*)?\r?\n(?:Content-Type:[^\r\n]*\r?\n)?\r?\n"
    rb"([^\r\n-]*)",
    re.I,
)


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


def is_html_csrf_exempt(path: str) -> bool:
    """Paths never checked by HtmlCsrfMiddleware (/api, webhooks, health, static)."""
    p = path or "/"
    if p.startswith(_EXEMPT_PREFIXES):
        return True
    # webapp-auth lives under /api/; keep explicit for docs/tests
    if p.rstrip("/").endswith("/telegram/webapp-auth"):
        return True
    return False


def is_form_content_type(content_type: str | None) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    if not ct:
        # Browsers usually send urlencoded; empty CT still treated as form-like POST.
        return True
    return any(ct == marker or ct.startswith(marker) for marker in _FORM_CT)


def should_check_html_csrf(request: Request) -> bool:
    if request.method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    if is_html_csrf_exempt(request.url.path):
        return False
    ct = request.headers.get("content-type")
    if ct and "application/json" in ct.lower():
        return False
    return is_form_content_type(ct)


def extract_csrf_from_body(content_type: str | None, body: bytes) -> str | None:
    ct = (content_type or "").lower()
    if "multipart/form-data" in ct:
        m = _MULTIPART_TOKEN_RE.search(body or b"")
        if not m:
            return None
        return m.group(1).decode("utf-8", errors="replace").strip() or None
    # urlencoded (default)
    try:
        qs = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    except Exception:
        return None
    for key in ("csrf_token", "csrfmiddlewaretoken"):
        vals = qs.get(key)
        if vals and vals[0]:
            return vals[0]
    return None


def extract_csrf_token(request: Request, body: bytes) -> str | None:
    header = (
        request.headers.get("X-CSRF-Token")
        or request.headers.get("X-CSRFToken")
        or request.headers.get("x-csrf-token")
    )
    if header and header.strip():
        return header.strip()
    return extract_csrf_from_body(request.headers.get("content-type"), body)


async def _body_and_replay(request: Request) -> bytes:
    """Read body once and reinstall receive so downstream handlers still see it."""
    body = await request.body()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # noqa: SLF001 - Starlette body replay pattern
    return body


def _forbidden_response(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    msg = "Ошибка безопасности (CSRF). Обновите страницу и попробуйте снова."
    if "text/html" in accept:
        return HTMLResponse(
            f"<!DOCTYPE html><html><body><p>{msg}</p>"
            f'<p><a href="{request.url.path}">Обновить</a></p></body></html>',
            status_code=403,
        )
    return PlainTextResponse(msg, status_code=403)


class HtmlCsrfMiddleware(BaseHTTPMiddleware):
    """Gate HTML form POSTs; /api/* and JSON stay on per-route CSRF."""

    async def dispatch(self, request: Request, call_next):
        from app.config import get_settings

        mode = (get_settings().csrf_html_mode or "off").strip().lower()
        if mode not in ("log", "enforce"):
            return await call_next(request)
        if not should_check_html_csrf(request):
            return await call_next(request)

        body = await _body_and_replay(request)
        token = extract_csrf_token(request, body)
        ok = validate_csrf_token(request, token)
        if ok:
            return await call_next(request)

        logger.warning(
            "csrf_html_%s path=%s method=%s has_token=%s session=%s",
            "missing" if not token else "invalid",
            request.url.path,
            request.method,
            int(bool(token)),
            int("session" in request.scope and bool(request.session.get("csrf_token"))),
        )
        if mode == "enforce":
            return _forbidden_response(request)
        return await call_next(request)
