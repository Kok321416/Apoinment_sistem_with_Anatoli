from starlette.requests import Request

from app.services.ops_alerts import (
    bound_alert_chat_ids,
    classify_client_channel,
    format_ops_alert,
    is_ops_alert_user,
    maybe_bind_ops_alert_chat,
    notify_health_if_bad,
    notify_ops_alert,
)


def _ua_request(ua: str, path: str = "/tg/", query: str = "") -> Request:
    qs = query.encode() if query else b""
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": qs,
            "headers": [(b"user-agent", ua.encode())],
            "client": ("1.1.1.1", 123),
            "server": ("test", 443),
        }
    )


def test_ops_username_match(monkeypatch):
    monkeypatch.setattr("app.services.ops_alerts.ops_alert_username", lambda: "andrievskypsy")
    assert is_ops_alert_user("andrievskypsy")
    assert is_ops_alert_user("@AndrievskyPsy")
    assert not is_ops_alert_user("someone_else")


def test_bind_only_operator(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.ops_alerts._recipients_path", lambda: tmp_path / "ops.json")
    monkeypatch.setattr("app.services.ops_alerts.ops_alert_username", lambda: "andrievskypsy")
    assert maybe_bind_ops_alert_chat(111, "other") is False
    assert bound_alert_chat_ids() == []
    assert maybe_bind_ops_alert_chat(999001, "andrievskypsy") is True
    assert bound_alert_chat_ids() == ["999001"]


def test_classify_channels():
    assert classify_client_channel(_ua_request("Mozilla Telegram/10.0")) == "Mini App"
    assert classify_client_channel(_ua_request("Mozilla Capacitor/6.0")) == "Capacitor"
    native = _ua_request("Mozilla/5.0 Chrome/120", query="client=native")
    assert classify_client_channel(native) == "Capacitor"
    assert classify_client_channel(_ua_request("Mozilla/5.0 Chrome/120")) == "сайт"


def test_format_escapes_html():
    text = format_ops_alert(
        kind="exception",
        path="/tg/",
        method="GET",
        status_code=500,
        message="<script>x</script>",
        traceback_text="line <boom>",
        channel="Mini App",
        user_agent="Telegram",
    )
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "Mini App" in text
    assert "500" in text


def test_notify_skipped_in_debug(monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.ops_alerts.get_settings", lambda: type("S", (), {"debug": True})())
    monkeypatch.setattr("app.services.telegram.send_telegram_async", lambda *a, **k: sent.append(a))
    assert notify_ops_alert(kind="exception", message="boom") is False
    assert sent == []


def test_health_ignores_ok_and_unconfigured_redis(monkeypatch):
    called = []
    monkeypatch.setattr("app.services.ops_alerts.notify_ops_alert", lambda **kw: called.append(kw))
    notify_health_if_bad(
        {"status": "ok", "schema": {"degraded": False}, "redis": {"configured": False, "ok": False}}
    )
    assert called == []
    notify_health_if_bad(
        {"status": "degraded", "schema": {"degraded": True, "reason": "missing col"}, "redis": {"configured": False}}
    )
    assert called and called[0]["kind"] == "health"
