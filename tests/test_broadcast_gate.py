"""Broadcast dry-run gate tests."""
from app.services.broadcast import AUDIENCE_CLIENTS


class _FakeSession(dict):
    scope = {"session": True}


class _FakeRequest:
    def __init__(self):
        self.scope = {"session": {}}
        self.session = self.scope["session"]


def test_dry_run_gate_blocks_without_run(monkeypatch):
    from app.services import broadcast_gate

    monkeypatch.setattr(broadcast_gate, "broadcast_require_dry_run", lambda: True)
    req = _FakeRequest()
    ok, err = broadcast_gate.dry_run_allows_enqueue(req, AUDIENCE_CLIENTS, 5)
    assert not ok
    assert err


def test_dry_run_gate_allows_after_record(monkeypatch):
    from app.services import broadcast_gate

    monkeypatch.setattr(broadcast_gate, "broadcast_require_dry_run", lambda: True)
    req = _FakeRequest()
    broadcast_gate.record_dry_run(req, AUDIENCE_CLIENTS, 5)
    ok, err = broadcast_gate.dry_run_allows_enqueue(req, AUDIENCE_CLIENTS, 5)
    assert ok and err is None


def test_test_self_skips_gate(monkeypatch):
    from app.services import broadcast_gate

    monkeypatch.setattr(broadcast_gate, "broadcast_require_dry_run", lambda: True)
    req = _FakeRequest()
    ok, _ = broadcast_gate.dry_run_allows_enqueue(req, "test_self", 1)
    assert ok
