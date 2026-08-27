"""Telegram WebView detection."""
from starlette.requests import Request

from app.services.telegram_webview import is_telegram_webview


def test_is_telegram_webview_user_agent():
    scope = {
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 Telegram/10.0")],
    }
    assert is_telegram_webview(Request(scope)) is True

    scope2 = {
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 Chrome/120.0")],
    }
    assert is_telegram_webview(Request(scope2)) is False
