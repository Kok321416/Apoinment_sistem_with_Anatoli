"""Signed HTTP calls from bot process to FastAPI backend."""
import hashlib
import hmac
import json
import time

import requests

from bot.config import get_bot_settings


def _sign_body(body: bytes, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    message = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return ts, sig


def post_site_api(path: str, payload: dict, *, timeout: int = 15) -> tuple[int, dict | None]:
    settings = get_bot_settings()
    site_url = settings.site_url.rstrip("/")
    token = settings.telegram_bot_token
    api_secret = settings.bot_api_secret
    if not token or not site_url.startswith("http"):
        return 0, None

    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_secret:
        ts, sig = _sign_body(body, api_secret)
        headers["X-Bot-Timestamp"] = ts
        headers["X-Bot-Signature"] = sig
    else:
        headers["X-Bot-Token"] = token

    try:
        r = requests.post(f"{site_url}{path}", data=body, headers=headers, timeout=timeout)
        data = r.json() if r.text else {}
        return r.status_code, data
    except Exception:
        return 0, None
