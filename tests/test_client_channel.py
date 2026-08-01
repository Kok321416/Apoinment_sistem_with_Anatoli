"""Client channel helpers for web / native / Telegram Mini App auth return."""
from app.services.client_channel import (
    normalize_client_channel,
    parse_tg_startapp_param,
    telegram_complete_urls,
    tg_mini_app_direct_link,
    tg_startapp_param,
    with_client_query,
)


def test_normalize_client_channel():
    assert normalize_client_channel("tg") == "tg"
    assert normalize_client_channel("miniapp") == "tg"
    assert normalize_client_channel("native") == "native"
    assert normalize_client_channel(None) == "web"


def test_tg_startapp_roundtrip():
    assert tg_startapp_param(kind="complete", token="abc-123") == "cmp_abc-123"
    assert tg_startapp_param(kind="handoff", token="tok_1") == "hnd_tok_1"
    assert parse_tg_startapp_param("cmp_abc-123") == ("complete", "abc-123")
    assert parse_tg_startapp_param("hnd_tok_1") == ("handoff", "tok_1")
    assert parse_tg_startapp_param("open") is None


def test_telegram_complete_urls_tg_uses_bridge():
    payload = telegram_complete_urls(
        site_url="https://allyourclients.ru",
        complete_token="tok123",
        client_channel="tg",
    )
    assert payload["client_channel"] == "tg"
    assert "/accounts/open-tg-app/" in payload["complete_url"]
    assert "kind=complete" in payload["complete_url"]
    assert "Вернуться" in payload["button_label"]


def test_tg_mini_app_direct_link():
    link = tg_mini_app_direct_link(bot_username="@MyBot", start_param="cmp_x")
    assert link == "https://t.me/MyBot?startapp=cmp_x"


def test_with_client_query():
    assert with_client_query("/register/?next=/tg/", "tg") == "/register/?next=/tg/&client=tg"
    assert with_client_query("/login/", "web") == "/login/"
