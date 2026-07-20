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


def _sign_body(body: bytes, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    message = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return ts, sig


def _api_base_urls() -> list[str]:
    settings = get_bot_settings()
    urls: list[str] = []
    for raw in (settings.site_internal_url, settings.site_url):
        url = (raw or "").strip().rstrip("/")
        if url.startswith("http") and url not in urls:
            urls.append(url)
    return urls


def post_site_api(path: str, payload: dict, *, timeout: int = 15) -> tuple[int, dict | None]:
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

    last_error: Exception | None = None
    for base in _api_base_urls():
        url = f"{base}{path}"
        try:
            r = requests.post(url, data=body, headers=headers, timeout=timeout)
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
