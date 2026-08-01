"""Client channel for auth return: web browser, Capacitor native, Telegram Mini App."""
from __future__ import annotations

from urllib.parse import quote

# Capacitor / Android custom scheme (intent-filter in mobile/android)
NATIVE_SCHEME = "allyourclients"
NATIVE_CHANNELS = frozenset({"native", "app", "capacitor", "android", "ios"})
TG_CHANNELS = frozenset({"tg", "telegram", "miniapp", "mini_app", "webapp"})


def normalize_client_channel(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in NATIVE_CHANNELS:
        return "native"
    if value in TG_CHANNELS:
        return "tg"
    return "web"


def telegram_complete_urls(*, site_url: str, complete_token: str, client_channel: str) -> dict[str, str]:
    """HTTPS always works; native uses HTTPS bridge page (Telegram buttons require http/https)."""
    site = (site_url or "").rstrip("/")
    https_url = f"{site}/accounts/telegram/complete/{complete_token}/"
    channel = normalize_client_channel(client_channel)
    if channel == "native":
        # Bridge page opens custom scheme; Telegram inline URL buttons only allow http(s).
        bridge = f"{site}/accounts/open-native/?kind=complete&token={quote(complete_token)}"
        return {
            "client_channel": channel,
            "complete_url": bridge,
            "https_url": https_url,
            "button_label": "Открыть приложение",
            "success_hint": "Нажмите кнопку ниже, чтобы вернуться в приложение и завершить вход.",
        }
    if channel == "tg":
        return {
            "client_channel": channel,
            "complete_url": https_url,
            "https_url": https_url,
            "button_label": "Открыть сервис",
            "success_hint": "Вернитесь в мини-приложение — вход завершится сам, или нажмите кнопку ниже.",
        }
    return {
        "client_channel": channel,
        "complete_url": https_url,
        "https_url": https_url,
        "button_label": "Открыть сайт",
        "success_hint": "Нажмите кнопку ниже, чтобы завершить вход в браузере.",
    }


def native_handoff_deep_link(token: str) -> str:
    return f"{NATIVE_SCHEME}://auth/handoff/{token}"


def native_handoff_https(*, site_url: str, token: str) -> str:
    site = (site_url or "").rstrip("/")
    return f"{site}/accounts/native-handoff/{token}/"


def with_client_query(url: str, client_channel: str) -> str:
    """Append client= to a relative or absolute URL."""
    channel = normalize_client_channel(client_channel)
    if channel == "web" or not url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}client={quote(channel)}"
