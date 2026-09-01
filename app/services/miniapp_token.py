"""Short-lived signed token for Mini App API if WebView drops session cookies."""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

_SALT = "ayc-miniapp-v1"
_MAX_AGE = 15 * 60


def mint_miniapp_access_token(user_id: int) -> str:
    s = URLSafeTimedSerializer(get_settings().secret_key, salt=_SALT)
    return s.dumps({"uid": int(user_id)})


def read_miniapp_access_token(token: str, *, max_age: int = _MAX_AGE) -> int | None:
    raw = (token or "").strip()
    if not raw:
        return None
    s = URLSafeTimedSerializer(get_settings().secret_key, salt=_SALT)
    try:
        data = s.loads(raw, max_age=max_age)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        uid = int(data.get("uid"))
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def bearer_user_id(authorization: str | None) -> int | None:
    header = (authorization or "").strip()
    if len(header) < 8 or header[:7].lower() != "bearer ":
        return None
    return read_miniapp_access_token(header[7:].strip())
