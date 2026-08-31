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
