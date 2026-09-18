"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_in_memory_rate_limits():
    from app.services.rate_limit import clear_in_memory_rate_limits

    clear_in_memory_rate_limits()
    yield
    clear_in_memory_rate_limits()


@pytest.fixture(autouse=True)
def _isolate_settings_overrides():
    """Undo settings overrides a test left on the shared object (monkeypatch restores them as
    instance attributes, which then shadow class-level configuration in later tests)."""
    from app.config import restore_settings_instance_state, settings_instance_state

    snapshot = settings_instance_state()
    yield
    restore_settings_instance_state(snapshot)


@pytest.fixture(autouse=True)
def _reset_async_sessionmaker():
    """Drop any configure_async_sessionmaker() override so a fixture leak can't reach other tests."""
    from app.database import reset_async_sessionmaker

    yield
    reset_async_sessionmaker()
