"""get_settings() must hand out one object for the whole process.

Most modules do `settings = get_settings()` at import. While get_settings() built a fresh Settings on
every cache_clear(), one test clearing the cache silently detached every imported module from the
object later callers patched — /internal/cron/reminders/ answered 503 instead of reading the patched
secrets. These tests pin the identity invariant that keeps import-time captures valid.
"""
from __future__ import annotations

from app.config import (
    Settings,
    get_settings,
    restore_settings_instance_state,
    settings_instance_state,
    settings_overrides,
)


def test_identity_is_stable_across_cache_clear():
    before = get_settings()
    get_settings.cache_clear()

    assert get_settings() is before


def test_modules_capturing_settings_at_import_see_the_same_object():
    import app.main as main_module
    import app.routers.pages as pages_module
    import app.services.telegram as telegram_module

    current = get_settings()
    for module in (main_module, pages_module, telegram_module):
        assert module.settings is current, f"{module.__name__} captured a different Settings object"


def test_class_level_override_is_visible_through_the_singleton(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(Settings, "telegram_bot_username", "contract_bot")

    assert settings.telegram_bot_username == "contract_bot"
    get_settings.cache_clear()
    assert get_settings().telegram_bot_username == "contract_bot"


def test_instance_override_is_visible_to_importers(monkeypatch):
    import app.services.telegram as telegram_module

    monkeypatch.setattr(get_settings(), "telegram_bot_token", "contract-token")

    assert telegram_module.settings.telegram_bot_token == "contract-token"


def test_settings_overrides_leaves_no_shadowing_attribute():
    before = settings_instance_state()

    with settings_overrides(telegram_bot_token="temporary") as settings:
        assert settings.telegram_bot_token == "temporary"

    assert settings_instance_state() == before
    assert "telegram_bot_token" not in get_settings().__dict__


def test_restore_drops_overrides_that_shadow_class_defaults(monkeypatch):
    snapshot = settings_instance_state()
    get_settings().telegram_bot_username = "leftover"

    restore_settings_instance_state(snapshot)

    monkeypatch.setattr(Settings, "telegram_bot_username", "from_class")
    assert get_settings().telegram_bot_username == "from_class"
