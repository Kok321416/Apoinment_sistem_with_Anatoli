from fastapi.testclient import TestClient


def test_webapp_diag_accepts_beacon(monkeypatch):
    monkeypatch.setattr("app.services.platform_errors.record_platform_error", lambda **k: None)
    monkeypatch.setattr("app.services.ops_alerts.notify_ops_alert", lambda **k: False)
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/telegram/webapp-diag",
        json={"kind": "js_error", "path": "/tg/", "platform": "ios", "extra": "boom", "ua": "Telegram"},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_webapp_diag_js_error_skips_ops_alert(monkeypatch):
    alerts = []
    monkeypatch.setattr("app.services.platform_errors.record_platform_error", lambda **k: None)
    monkeypatch.setattr(
        "app.services.ops_alerts.notify_ops_alert",
        lambda **k: alerts.append(k) or False,
    )
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/telegram/webapp-diag",
        json={
            "kind": "js_error",
            "path": "/booking/",
            "platform": "ios",
            "extra": "Script error.",
            "ua": "Telegram",
        },
    )
    assert r.status_code == 200
    assert alerts == []


def test_webapp_diag_auth_fail_still_alerts(monkeypatch):
    alerts = []
    monkeypatch.setattr("app.services.platform_errors.record_platform_error", lambda **k: None)
    monkeypatch.setattr(
        "app.services.ops_alerts.notify_ops_alert",
        lambda **k: alerts.append(k.get("message")) or False,
    )
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/telegram/webapp-diag",
        json={"kind": "auth_fail", "path": "/tg/", "platform": "android", "extra": "bad", "ua": "Telegram"},
    )
    assert r.status_code == 200
    assert len(alerts) == 1
    assert "auth_fail" in (alerts[0] or "")
