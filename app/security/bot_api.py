"""Verify requests from the Telegram bot process."""
import hashlib
import hmac
import time

from fastapi import Request

from app.config import get_settings

_MAX_SKEW_SECONDS = 300


def verify_bot_request(request: Request, body: bytes) -> bool:
    settings = get_settings()
    # When BOT_API_SECRET is set, only HMAC signature is accepted (not raw bot token).
    if settings.bot_api_secret:
        ts_raw = (request.headers.get("X-Bot-Timestamp") or "").strip()
        sig = (request.headers.get("X-Bot-Signature") or "").strip()
        if not ts_raw or not sig:
            return False
        try:
            ts = int(ts_raw)
        except ValueError:
            return False
        if abs(time.time() - ts) > _MAX_SKEW_SECONDS:
            return False
        message = f"{ts}.".encode() + body
        expected = hmac.new(settings.bot_api_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    header_token = (request.headers.get("X-Bot-Token") or "").strip()
    if not header_token or not settings.telegram_bot_token:
        return False
    return hmac.compare_digest(header_token, settings.telegram_bot_token)


def sign_bot_body(body: bytes, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    message = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return ts, sig
