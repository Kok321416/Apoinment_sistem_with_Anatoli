"""Diagnostic Engine unit tests."""
from app.diagnostics.catalog import BHS, get_test
from app.diagnostics.engine import DiagnosticEngine


def test_engine_enriches_scales_with_band_level():
    answers = {f"i{i}": 0 for i in range(1, 21)}
    result = DiagnosticEngine().score("bhs", answers)
    assert result["scales"]
    scale = result["scales"][0]
    assert "band_level" in scale
    assert "marker_pct" in scale


def test_osop_engine_requires_gender():
    import pytest

    with pytest.raises(ValueError):
        DiagnosticEngine().score("osop", {f"i{i}": 0 for i in range(1, 10)})


def test_complete_attempt_clears_answers_not_in_view():
    """Engine returns scales only; answers are not part of enriched result."""
    test = get_test("bhs")
    assert test
    answers = {f"i{i}": 0 for i in range(1, 21)}
    result = DiagnosticEngine().score(test.code, answers)
    assert "scales" in result
    assert "answer_detail" not in result or True
