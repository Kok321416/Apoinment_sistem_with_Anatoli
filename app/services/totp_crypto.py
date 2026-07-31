"""Shared TOTP helpers (stdlib only). Used by admin and specialist 2FA."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from app.config import get_settings


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    sec = (secret or "").strip().upper().replace(" ", "")
    padding = "=" * ((8 - len(sec) % 8) % 8)
    return base64.b32decode(sec + padding, casefold=True)


def totp_at(secret: str, counter: int) -> str:
    key = _decode_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    now_counter = int(time.time()) // 30
    for offset in range(-window, window + 1):
        if totp_at(secret, now_counter + offset) == code:
            return True
    return False


def provisioning_uri(secret: str, email: str) -> str:
    settings = get_settings()
    issuer = settings.site_brand_name or "AllYourClients"
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"
