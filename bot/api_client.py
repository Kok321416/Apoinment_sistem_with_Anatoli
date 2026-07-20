"""Signed HTTP calls from bot process to FastAPI backend."""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlparse

import requests

from bot.config import get_bot_settings

logger = logging.getLogger(__name__)

_session = requests.Session()


def _sign_body(body: bytes, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    message = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return ts, sig


def _api_targets(timeout: int) -> list[tuple[str, int]]:
    """Public HTTPS first; optional internal URL with short timeout only."""
    settings = get_bot_settings()
    targets: list[tuple[str, int]] = []
    public = (settings.site_url or "").strip().rstrip("/")
    internal = (settings.site_internal_url or "").strip().rstrip("/")
    if public.startswith("http"):
        targets.append((public, timeout))
    if internal.startswith("http") and internal.rstrip("/") != public.rstrip("/"):
        targets.append((internal, min(3, timeout)))
    return targets


def post_site_api(path: str, payload: dict, *, timeout: int = 8) -> tuple[int, dict | None]:
    settings = get_bot_settings()
    token = settings.telegram_bot_token
    api_secret = settings.bot_api_secret
    if not token:
        return 0, None

    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_secret:
        ts, sig = _sign_body(body, api_secret)
        headers["X-Bot-Timestamp"] = ts
        headers["X-Bot-Signature"] = sig
    else:
        headers["X-Bot-Token"] = token

    public_host = urlparse(settings.site_url).netloc
    if public_host:
        headers.setdefault("Host", public_host)

    targets = _api_targets(timeout)
    if not targets:
        logger.error("SITE_URL is not configured for bot API calls")
        return 0, None

    last_error: Exception | None = None
    for base, req_timeout in targets:
        url = f"{base.rstrip('/')}{path}"
        try:
            r = _session.post(url, data=body, headers=headers, timeout=(3, req_timeout))
            data = r.json() if r.text else {}
            if r.status_code >= 500:
                logger.warning("Site API %s returned HTTP %s", url, r.status_code)
                continue
            return r.status_code, data
        except Exception as exc:
            last_error = exc
            logger.warning("Site API request failed for %s: %s", url, exc)

    if last_error:
        logger.error("All Site API endpoints failed for %s", path)
    return 0, None
