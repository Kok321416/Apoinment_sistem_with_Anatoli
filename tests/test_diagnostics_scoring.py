"""Unit tests for diagnostic scoring plugins (no invented bands)."""
from app.diagnostics.catalog import BHS, get_test, list_tests, score_bhs


def test_catalog_has_requested_codes():
    codes = {t.code for t in list_tests()}
    assert "bhs" in codes
    assert "bdi" in codes
    assert "schmischek" in codes
    assert "rmet" in codes
    assert "wcq" in codes
    assert "osop" in codes


def test_bhs_all_non_keyed_minimal():
    # Answer False on True-keyed items and True on False-keyed → score 0
    answers = {}
    for i in range(1, 21):
        # True-keyed items: answer False (0); False-keyed: answer True (1)
        from app.diagnostics.catalog import _BHS_TRUE_KEYS

        answers[f"i{i}"] = 0 if i in _BHS_TRUE_KEYS else 1
    result = score_bhs(answers, BHS)
    assert result["scores"]["total"] == 0
    assert result["scales"][0]["band_label"] == "минимальная"


def test_bhs_max_severe():
    from app.diagnostics.catalog import _BHS_TRUE_KEYS

    answers = {}
    for i in range(1, 21):
        answers[f"i{i}"] = 1 if i in _BHS_TRUE_KEYS else 0
    result = score_bhs(answers, BHS)
    assert result["scores"]["total"] == 20
    assert result["scales"][0]["band_label"] == "выраженная"
    assert "attention_high" in result["flags"]


def test_pending_not_runnable():
    assert get_test("wcq") is not None
    assert get_test("wcq").runnable is False
    assert get_test("bhs").runnable is True
