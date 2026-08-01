"""Client channel for auth return: web browser, Capacitor native, Telegram Mini App."""
from __future__ import annotations

from urllib.parse import quote

# Capacitor / Android custom scheme (intent-filter in mobile/android)
NATIVE_SCHEME = "allyourclients"
NATIVE_CHANNELS = frozenset({"native", "app", "capacitor", "android", "ios"})
TG_CHANNELS = frozenset({"tg", "telegram", "miniapp", "mini_app", "webapp"})

# Telegram startapp: A-Z a-z 0-9 _ - ; consumed in telegram-webapp.js
TG_STARTAPP_COMPLETE_PREFIX = "cmp_"
TG_STARTAPP_HANDOFF_PREFIX = "hnd_"


def normalize_client_channel(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in NATIVE_CHANNELS:
        return "native"
    if value in TG_CHANNELS:
        return "tg"
    return "web"


def tg_startapp_param(*, kind: str, token: str) -> str:
    """Build startapp value for reopening Mini App after external auth."""
    clean = (token or "").strip()
    if kind == "complete":
        return f"{TG_STARTAPP_COMPLETE_PREFIX}{clean}"
    return f"{TG_STARTAPP_HANDOFF_PREFIX}{clean}"


def parse_tg_startapp_param(raw: str | None) -> tuple[str, str] | None:
    """Return (kind, token) for cmp_/hnd_ start_param, else None."""
    value = (raw or "").strip()
    if value.startswith(TG_STARTAPP_COMPLETE_PREFIX):
        token = value[len(TG_STARTAPP_COMPLETE_PREFIX) :]
        return ("complete", token) if token else None
    if value.startswith(TG_STARTAPP_HANDOFF_PREFIX):
        token = value[len(TG_STARTAPP_HANDOFF_PREFIX) :]
        return ("handoff", token) if token else None
    return None


def tg_mini_app_direct_link(*, bot_username: str, start_param: str) -> str:
    """https://t.me/<bot>?startapp=<param> reopens the bot Menu Mini App."""
    bot = (bot_username or "").lstrip("@").strip()
    param = (start_param or "").strip()
    if not bot or not param:
        return ""
    return f"https://t.me/{bot}?startapp={quote(param, safe='')}"


def telegram_complete_urls(*, site_url: str, complete_token: str, client_channel: str) -> dict[str, str]:
    """HTTPS always works; native/tg use HTTPS bridge pages (Telegram buttons require http/https)."""
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
        # Bridge opens t.me/?startapp= so session is created inside Mini App WebView.
        bridge = f"{site}/accounts/open-tg-app/?kind=complete&token={quote(complete_token)}"
        return {
            "client_channel": channel,
            "complete_url": bridge,
            "https_url": https_url,
            "button_label": "Вернуться в приложение",
            "success_hint": "Нажмите кнопку ниже, чтобы вернуться в мини-приложение и завершить вход.",
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
