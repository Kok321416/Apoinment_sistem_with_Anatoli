"""Unit tests for diagnostic scoring plugins (no invented bands)."""
from app.diagnostics.catalog import BHS, get_test, list_tests, score_bhs
from app.services.diagnostics_service import missing_answer_ids, parse_diagnostic_answers


def test_parse_diagnostic_answers_ignores_meta_fields():
    items = [
        ("csrf_token", "abc"),
        ("source", "profile"),
        ("i1", "2"),
        ("i2", "0"),
        ("booking_id", "5"),
    ]
    assert parse_diagnostic_answers(items) == {"i1": "2", "i2": "0"}


def test_missing_answer_ids_detects_gaps():
    test = get_test("bhs")
    answers = {f"i{i}": "0" for i in range(1, 20)}
    missing = missing_answer_ids(test, answers)
    assert missing == ["i20"]


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


def test_runnable_tests_have_russian_instruction():
    for code in ("bhs", "bdi", "wcq", "schmischek", "osop"):
        test = get_test(code)
        assert test and test.runnable
        assert test.instruction
        assert any(ord(c) > 127 for c in test.instruction)


def test_runnable_and_pending():
    assert get_test("wcq") is not None
    assert get_test("wcq").runnable is True
    assert get_test("schmischek").runnable is True
    assert get_test("osop").runnable is True
    assert get_test("bhs").runnable is True
    assert get_test("bdi").runnable is True
    assert get_test("rmet").runnable is False


def test_wcq_scoring_returns_eight_scales():
    from app.diagnostics.catalog import WCQ, score_wcq

    answers = {f"i{i}": 2 for i in range(1, 33)}
    result = score_wcq(answers, WCQ)
    assert len(result["scales"]) == 8
    assert "Профиль" in result["summary"]
