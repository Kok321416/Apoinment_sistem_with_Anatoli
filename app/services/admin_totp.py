"""TOTP 2FA for platform admins (stdlib only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminTwoFactor, User


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
    issuer = settings.site_brand_name or "Platform"
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def get_admin_2fa(db: Session, user_id: int) -> AdminTwoFactor | None:
    return db.get(AdminTwoFactor, user_id)


def admin_2fa_enabled(db: Session, user_id: int) -> bool:
    row = get_admin_2fa(db, user_id)
    return bool(row and row.enabled and row.secret)


def needs_admin_2fa(db: Session, user: User) -> bool:
    if not (user.is_staff or user.is_superuser):
        return False
    return admin_2fa_enabled(db, user.id)


def ensure_admin_2fa_setup(db: Session, user: User) -> AdminTwoFactor:
    row = get_admin_2fa(db, user.id)
    if row:
        return row
    row = AdminTwoFactor(user_id=user.id, secret=generate_totp_secret(), enabled=False, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enable_admin_2fa(db: Session, user: User, code: str) -> tuple[bool, str]:
    row = ensure_admin_2fa_setup(db, user)
    if not verify_totp(row.secret, code):
        return False, "Неверный код"
    row.enabled = True
    row.enabled_at = datetime.utcnow()
    db.commit()
    return True, "2FA включена"


def disable_admin_2fa(db: Session, user_id: int) -> None:
    row = get_admin_2fa(db, user_id)
    if row:
        db.delete(row)
        db.commit()


def verify_admin_2fa_login(db: Session, user_id: int, code: str) -> bool:
    row = get_admin_2fa(db, user_id)
    if not row or not row.enabled:
        return True
    return verify_totp(row.secret, code)
