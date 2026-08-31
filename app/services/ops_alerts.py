"""Critical ops alerts to a private Telegram chat (operator only).

Telegram bots cannot DM by @username until that user has written to the bot.
We persist chat_id after @andrievskypsy (or ADMIN_TELEGRAM_USERNAME) messages the bot.
"""
from __future__ import annotations

import html
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Request

from app.config import get_settings
from app.services.client_channel import NATIVE_CHANNELS
from app.services.redis_client import redis_get, redis_set
from app.services.telegram_webview import is_telegram_webview

logger = logging.getLogger(__name__)

DEFAULT_OPS_USERNAME = "andrievskypsy"
_COOLDOWN_SEC = 10 * 60
_HEALTH_COOLDOWN_SEC = 30 * 60
_MAX_TG = 3900

_file_lock = threading.Lock()
_mem_lock = threading.Lock()
_mem_until: dict[str, float] = {}
_missing_chat_logged = False


def ops_alert_username() -> str:
    settings = get_settings()
    raw = (getattr(settings, "admin_telegram_username", "") or "").strip().lstrip("@")
    return (raw or DEFAULT_OPS_USERNAME).lower()


def is_ops_alert_user(username: str | None) -> bool:
    if not username:
        return False
    return username.strip().lstrip("@").lower() == ops_alert_username()


def _recipients_path() -> Path:
    root = get_settings().media_root
    root.mkdir(parents=True, exist_ok=True)
    return root / "ops_alert_recipients.json"


def env_alert_chat_ids() -> list[str]:
    raw = (getattr(get_settings(), "telegram_alert_chat_ids", "") or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        cid = part.strip()
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def bound_alert_chat_ids() -> list[str]:
    path = _recipients_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    ids = data.get("chat_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return []
    out: list[str] = []
    for item in ids:
        cid = str(item).strip()
        if cid and cid not in out:
            out.append(cid)
    return out


def recipient_chat_ids() -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for cid in [*env_alert_chat_ids(), *bound_alert_chat_ids()]:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def maybe_bind_ops_alert_chat(chat_id: int | str | None, username: str | None) -> bool:
    """Save chat_id only when Telegram username matches the operator."""
    if chat_id is None or not is_ops_alert_user(username):
        return False
    cid = str(chat_id).strip()
    if not cid:
        return False
    path = _recipients_path()
    with _file_lock:
        ids = bound_alert_chat_ids()
        if cid not in ids:
            ids.append(cid)
        payload = {
            "username": ops_alert_username(),
            "chat_ids": ids,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("ops alerts bound chat_id=%s user=@%s", cid, ops_alert_username())
    return True


def classify_client_channel(request: Request) -> str:
    q = (request.query_params.get("client") or "").strip().lower()
    if q in NATIVE_CHANNELS:
        return "Capacitor"
    ua = (request.headers.get("user-agent") or "").lower()
    if "capacitor" in ua:
        return "Capacitor"
    if is_telegram_webview(request):
        return "Mini App"
    return "сайт"


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _trim_tb(tb: str | None, limit: int = 1400) -> str:
    text = (tb or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return "…\n" + text[-limit:]


def format_ops_alert(
    *,
    kind: str,
    path: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    message: str | None = None,
    traceback_text: str | None = None,
    channel: str | None = None,
    user_agent: str | None = None,
    user_id: int | None = None,
    ip: str | None = None,
) -> str:
    title = {
        "exception": "Необработанное исключение",
        "http_5xx": "Ответ 5xx",
        "health": "Health degraded",
    }.get(kind, kind)
    lines = [f"🚨 <b>{_esc(title)}</b>"]
    if status_code is not None:
        lines.append(f"Статус: <code>{_esc(status_code)}</code>")
    if channel:
        lines.append(f"Канал: {_esc(channel)}")
    if method or path:
        lines.append(f"<code>{_esc(method or '')} {_esc(path or '')}</code>".strip())
    if user_id is not None:
        lines.append(f"user_id: <code>{_esc(user_id)}</code>")
    if ip:
        lines.append(f"IP: <code>{_esc(ip)}</code>")
    ua = (user_agent or "").strip()
    if ua:
        lines.append(f"UA: <code>{_esc(ua[:180])}</code>")
    if message:
        lines.append(_esc(message)[:500])
    tb = _trim_tb(traceback_text)
    if tb:
        lines.append(f"<pre>{_esc(tb)}</pre>")
    text = "\n".join(lines)
    if len(text) > _MAX_TG:
        return text[:_MAX_TG] + "…"
    return text


def _cooldown_allows(fingerprint: str, ttl_sec: int) -> bool:
    key = f"ops_alert:{fingerprint}"
    now = time.time()
    cached = redis_get(key)
    if cached:
        return False
    with _mem_lock:
        until = _mem_until.get(key, 0)
        if until > now:
            return False
        _mem_until[key] = now + ttl_sec
        if len(_mem_until) > 500:
            dead = [k for k, exp in _mem_until.items() if exp <= now]
            for k in dead:
                _mem_until.pop(k, None)
    redis_set(key, "1", ttl_sec=ttl_sec)
    return True


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def notify_ops_alert(
    *,
    kind: str,
    path: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    message: str | None = None,
    traceback_text: str | None = None,
    request: Request | None = None,
    user_id: int | None = None,
    ip: str | None = None,
) -> bool:
    """Fire-and-forget Telegram alert. Never raises. No-op in DEBUG."""
    settings = get_settings()
    if settings.debug:
        return False
    channel = None
    ua = None
    if request is not None:
        channel = classify_client_channel(request)
        ua = request.headers.get("user-agent")
        path = path or str(request.url.path)
        method = method or request.method
        if ip is None:
            ip = client_ip(request)
    fp = "|".join(
        [
            kind,
            method or "",
            (path or "")[:180],
            str(status_code or ""),
            (message or "")[:80],
        ]
    )
    ttl = _HEALTH_COOLDOWN_SEC if kind == "health" else _COOLDOWN_SEC
    if not _cooldown_allows(fp, ttl):
        return False
    chats = recipient_chat_ids()
    if not chats:
        global _missing_chat_logged
        if not _missing_chat_logged:
            _missing_chat_logged = True
            logger.warning(
                "ops alerts: нет chat_id. Напишите боту /start или /alerts с аккаунта @%s",
                ops_alert_username(),
            )
        return False
    text = format_ops_alert(
        kind=kind,
        path=path,
        method=method,
        status_code=status_code,
        message=message,
        traceback_text=traceback_text,
        channel=channel,
        user_agent=ua,
        user_id=user_id,
        ip=ip,
    )
    try:
        from app.services.telegram import send_telegram_async

        for chat_id in chats:
            send_telegram_async(chat_id, text)
        return True
    except Exception:
        logger.warning("ops alert send failed", exc_info=True)
        return False


def notify_health_if_bad(payload: dict) -> None:
    schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
    redis = payload.get("redis") if isinstance(payload.get("redis"), dict) else {}
    parts: list[str] = []
    if schema.get("degraded"):
        parts.append(f"schema: {schema.get('reason') or schema.get('error') or 'degraded'}")
    if redis.get("configured") and not redis.get("ok"):
        parts.append(f"redis: {redis.get('error') or redis.get('mode') or 'down'}")
    status = payload.get("status")
    if status and status not in ("ok",) and not parts:
        parts.append(str(status))
    if not parts:
        return
    notify_ops_alert(
        kind="health",
        path="/health",
        method="GET",
        status_code=200,
        message="; ".join(parts)[:500],
    )
