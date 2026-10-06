"""Phase 3: HTML CSRF middleware (log / enforce) + form helpers."""
from __future__ import annotations

import logging
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings_overrides
from app.security.csrf import (
    HtmlCsrfMiddleware,
    ensure_csrf_token,
    extract_csrf_from_body,
    is_form_content_type,
    is_html_csrf_exempt,
    should_check_html_csrf,
    validate_csrf_token,
)


def test_exempt_api_and_webhooks():
    assert is_html_csrf_exempt("/api/telegram/webapp-auth")
    assert is_html_csrf_exempt("/api/me")
    assert is_html_csrf_exempt("/telegram/webhook/secret")
    assert is_html_csrf_exempt("/internal/cron/reminders/")
    assert is_html_csrf_exempt("/health")
    assert is_html_csrf_exempt("/static/js/x.js")
    assert not is_html_csrf_exempt("/login/")
    assert not is_html_csrf_exempt("/register/")
    assert not is_html_csrf_exempt("/booking/")


def test_form_content_type():
    assert is_form_content_type("application/x-www-form-urlencoded")
    assert is_form_content_type("multipart/form-data; boundary=xyz")
    assert is_form_content_type(None)
    assert is_form_content_type("")
    assert not is_form_content_type("application/json")


def test_extract_urlencoded_token():
    body = b"login=a&password=b&csrf_token=tok123"
    assert extract_csrf_from_body("application/x-www-form-urlencoded", body) == "tok123"
    assert extract_csrf_from_body("application/x-www-form-urlencoded", b"x=1") is None


def test_extract_multipart_token():
    body = (
        b"------bound\r\n"
        b'Content-Disposition: form-data; name="csrf_token"\r\n\r\n'
        b"abcXYZ\r\n"
        b"------bound\r\n"
        b'Content-Disposition: form-data; name="login"\r\n\r\n'
        b"user\r\n"
        b"------bound--"
    )
    assert extract_csrf_from_body("multipart/form-data; boundary=----bound", body) == "abcXYZ"


def test_should_check_skips_json_and_api():
    api = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/me"),
        headers={"content-type": "application/json"},
    )
    assert not should_check_html_csrf(api)
    form = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/login/"),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert should_check_html_csrf(form)
    get_req = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/login/"),
        headers={},
    )
    assert not should_check_html_csrf(get_req)


def _mini_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(HtmlCsrfMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test-csrf-secret", max_age=3600)

    @app.get("/form/")
    async def form_page(request: Request):
        token = ensure_csrf_token(request)
        return {"csrf_token": token}

    @app.post("/form/")
    async def form_post(request: Request):
        data = await request.form()
        return {"ok": True, "echo": data.get("login")}

    @app.post("/api/ping")
    async def api_ping():
        return {"ok": True}

    return TestClient(app)


def test_log_mode_allows_missing_csrf(caplog):
    client = _mini_app()
    with settings_overrides(csrf_html_mode="log"):
        with caplog.at_level(logging.WARNING, logger="app.security.csrf"):
            r = client.post("/form/", data={"login": "x"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert any("csrf_html_" in rec.message for rec in caplog.records)


def test_enforce_blocks_missing_csrf():
    client = _mini_app()
    with settings_overrides(csrf_html_mode="enforce"):
        r = client.post("/form/", data={"login": "x"})
        assert r.status_code == 403


def test_enforce_allows_valid_csrf():
    client = _mini_app()
    with settings_overrides(csrf_html_mode="enforce"):
        tok = client.get("/form/").json()["csrf_token"]
        r = client.post("/form/", data={"login": "ok", "csrf_token": tok})
        assert r.status_code == 200
        assert r.json()["echo"] == "ok"


def test_api_exempt_even_in_enforce():
    client = _mini_app()
    with settings_overrides(csrf_html_mode="enforce"):
        r = client.post("/api/ping", json={"x": 1})
        assert r.status_code == 200


def test_validate_helpers_roundtrip():
    req = SimpleNamespace(scope={"session": {}}, session={})
    assert validate_csrf_token(req, "nope") is False
    tok = ensure_csrf_token(req)
    assert validate_csrf_token(req, tok) is True
    assert validate_csrf_token(req, "wrong") is False
