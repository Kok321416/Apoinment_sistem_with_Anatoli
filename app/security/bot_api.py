"""Verify requests from the Telegram bot process."""
import hashlib
import hmac
import time

from fastapi import Request

from app.config import get_settings

_MAX_SKEW_SECONDS = 300


def _bot_secrets() -> list[str]:
    settings = get_settings()
    secrets: list[str] = []
    if settings.bot_api_secret:
        secrets.append(settings.bot_api_secret)
    if settings.telegram_bot_token:
        secrets.append(settings.telegram_bot_token)
    return secrets


def verify_bot_request(request: Request, body: bytes) -> bool:
    settings = get_settings()
    secrets = _bot_secrets()
    if not secrets:
        return False

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
        if hmac.compare_digest(expected, sig):
            return True

    header_token = (request.headers.get("X-Bot-Token") or "").strip()
    if not header_token:
        return False
    for secret in secrets:
        if hmac.compare_digest(header_token, secret):
            return True
    return False


def sign_bot_body(body: bytes, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    message = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return ts, sig
