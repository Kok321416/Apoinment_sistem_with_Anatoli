"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_in_memory_rate_limits():
    from app.services.rate_limit import clear_in_memory_rate_limits

    clear_in_memory_rate_limits()
    yield
    clear_in_memory_rate_limits()
