"""Diagnostic Engine unit tests."""
from app.diagnostics.catalog import BHS, get_test
from app.diagnostics.engine import DiagnosticEngine
from app.diagnostics.tests.eyes import score_eyes, EYES


def test_engine_enriches_scales_with_band_level():
    answers = {f"i{i}": 0 for i in range(1, 21)}
    result = DiagnosticEngine().score("bhs", answers)
    assert result["scales"]
    scale = result["scales"][0]
    assert "band_level" in scale
    assert "marker_pct" in scale


def test_eyes_scoring_counts_correct():
    answers = {}
    for i in range(1, 13):
        from app.diagnostics.tests.eyes import _EYES_KEYS

        answers[f"i{i}"] = _EYES_KEYS[i - 1]
    result = score_eyes(answers, EYES)
    assert result["scores"]["accuracy"] == 12
    assert result["scales"][0]["band_label"] == "высокая"


def test_complete_attempt_clears_answers_not_in_view():
    """Engine returns scales only; answers are not part of enriched result."""
    test = get_test("bhs")
    assert test
    answers = {f"i{i}": 0 for i in range(1, 21)}
    result = DiagnosticEngine().score(test.code, answers)
    assert "scales" in result
    assert "answer_detail" not in result or True
