"""Client gate from authenticated user for public specialist booking."""
from types import SimpleNamespace

from app.services.public_client import (
    apply_client_gate_from_user,
    client_gate_ok,
    set_client_gate,
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
    set_client_gate(session, consultant_id=1, name="A", email="", telegram="", verified=True)
    assert not client_gate_ok(session, 1)
    set_client_gate(session, consultant_id=1, name="A", email="a@b.c", verified=True)
    assert client_gate_ok(session, 1)
