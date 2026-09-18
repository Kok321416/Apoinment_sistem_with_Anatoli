"""Unit tests for statistics status filters and bulk delete."""
from __future__ import annotations

from datetime import date, time

from app.services.statistics_hub import parse_status_filters, status_filter_query


def test_parse_status_filters_empty_means_all():
    assert parse_status_filters(None) == []
    assert parse_status_filters([]) == []
    assert parse_status_filters(["", "  "]) == []


def test_parse_status_filters_cancelled_completed():
    assert parse_status_filters(["cancelled", "completed"]) == ["cancelled", "completed"]
    assert parse_status_filters(["cancelled,completed"]) == ["cancelled", "completed"]
    assert parse_status_filters(["CANCELLED", "nope"]) == ["cancelled"]


def test_status_filter_query():
    assert status_filter_query([]) == ""
    assert status_filter_query(["cancelled", "completed"]) == "status=cancelled&status=completed"
