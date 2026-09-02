"""Client gate from authenticated user for public specialist booking."""
from types import SimpleNamespace

from app.services.public_client import (
    apply_client_gate_from_user,
    client_gate_ok,
    set_client_gate,
    specialist_slug_from_public_path,
    sync_booking_session_from_gate,
)


def test_apply_client_gate_from_user_sets_verified_session():
    session = {}
    user = SimpleNamespace(
        id=7,
        email="client@example.com",
        first_name="Анна",
        last_name="Иванова",
        username="client@example.com",
        get_full_name=lambda: "Анна Иванова",
    )
    db = SimpleNamespace()
    db.query = lambda *a, **k: SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: None))

    apply_client_gate_from_user(db, session, consultant_id=42, user=user)
    assert client_gate_ok(session, 42)
    assert session["pc_name"] == "Анна Иванова"
    assert session["pc_email"] == "client@example.com"
    assert session["pc_verified"] is True


def test_set_client_gate_requires_contact():
    session = {}
    set_client_gate(session, consultant_id=1, name="A", phone="", telegram="", verified=True)
    assert not client_gate_ok(session, 1)
    set_client_gate(session, consultant_id=1, name="A", phone="+79991234567", verified=True)
    assert client_gate_ok(session, 1)
    set_client_gate(session, consultant_id=1, name="A", email="a@b.c", verified=True)
    assert client_gate_ok(session, 1)


def test_specialist_slug_from_public_path():
    assert specialist_slug_from_public_path("/s/anna-ivanova/") == "anna-ivanova"
    assert specialist_slug_from_public_path("/s/id-3/c/1/book/") == "id-3"
    assert specialist_slug_from_public_path("/login/") is None


def test_sync_booking_session_from_gate():
    session = {
        "pc_name": "Иван",
        "pc_phone": "+79991234567",
        "pc_telegram": "@ivan",
        "pc_email": "i@e.ru",
    }
    sync_booking_session_from_gate(session)
    assert session["booking_contact_done"] is True
    assert session["booking_client_name"] == "Иван"
    assert session["booking_client_phone"] == "+79991234567"


def test_serialize_card_includes_diagnostics_url():
    from datetime import date

    from app.services.clients_crm import serialize_card

    card = SimpleNamespace(
        id=12,
        name="Test",
        email="",
        phone="+79991234567",
        telegram="",
        notes="",
        created_at=None,
        updated_at=None,
    )
    data = serialize_card(card, {}, date.today())
    assert data["diagnostics_url"] == "/clients/12/#diagnostics"
