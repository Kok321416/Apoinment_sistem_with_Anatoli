"""Email registration flow tests."""
import re
import uuid

from fastapi.testclient import TestClient


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token not found on page"
    return match.group(1)


def test_email_registration_does_not_500(monkeypatch):
    from app.main import app

    sent = []

    def fake_send(to_email: str, code: str) -> bool:
        sent.append((to_email, code))
        return True

    monkeypatch.setattr("app.services.email_verification.send_verification_email", fake_send)

    client = TestClient(app)
    email = f"reg_{uuid.uuid4().hex[:8]}@example.com"
    csrf = _csrf_from_html(client.get("/register/").text)

    response = client.post(
        "/register/",
        data={
            "csrf_token": csrf,
            "auth_method": "email",
            "fio": "Иванов Иван Иванович",
            "phone": "+79991234567",
            "email": email,
            "password": "TestPass123!",
            "password_confirm": "TestPass123!",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text[:1500]
    assert "/accounts/verify-email/" in response.headers.get("location", "")
    assert sent and sent[0][0] == email
