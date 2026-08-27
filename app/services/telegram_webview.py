"""Detect Telegram Mini App / WebView from HTTP headers."""
from __future__ import annotations

from fastapi import Request


def is_telegram_webview(request: Request) -> bool:
    ua = (request.headers.get("user-agent") or "").lower()
    if "telegram" in ua:
        return True
    # Some Telegram Desktop / embedded clients.
    if request.headers.get("x-requested-with", "").lower() == "org.telegram.messenger":
        return True
    return False
