"""Tests for abuse protection helpers and rate-limit pruning."""
from app.security.request_guards import (
    is_auth_abuse_path,
    is_public_booking_write,
    should_skip_rate_limit,
)
from app.services.rate_limit import check_rate_limit, reset_rate_limit


def test_skip_static_and_health():
    assert should_skip_rate_limit("/static/css/app.css")
    assert should_skip_rate_limit("/media/x.png")
    assert should_skip_rate_limit("/health")
    assert not should_skip_rate_limit("/login/")


def test_auth_abuse_paths():
    assert is_auth_abuse_path("/login/", "POST")
    assert is_auth_abuse_path("/register/", "POST")
    assert is_auth_abuse_path("/api/auth/login", "POST")
    assert not is_auth_abuse_path("/calendars/", "GET")


def test_public_booking_write_paths():
    assert is_public_booking_write("/s/demo/c/1/", "POST")
    assert is_public_booking_write("/s/demo/welcome/", "POST")
    assert not is_public_booking_write("/s/demo/c/1/slots/", "GET")


def test_rate_limit_blocks_after_max():
    reset_rate_limit("sec-test-key")
    assert check_rate_limit("sec-test-key", max_calls=2, window_sec=60)
    assert check_rate_limit("sec-test-key", max_calls=2, window_sec=60)
    assert not check_rate_limit("sec-test-key", max_calls=2, window_sec=60)
    reset_rate_limit("sec-test-key")
