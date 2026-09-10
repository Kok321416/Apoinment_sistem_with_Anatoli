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
        ("gender", "f"),
    ]
    assert parse_diagnostic_answers(items) == {"i1": "2", "i2": "0", "gender": "f"}


def test_missing_answer_ids_detects_gaps():
    test = get_test("bhs")
    answers = {f"i{i}": "0" for i in range(1, 20)}
    missing = missing_answer_ids(test, answers)
    assert missing == ["i20"]


def test_catalog_has_requested_codes():
    tests = list_tests(only_runnable=True)
    codes = {t.code for t in tests}
    assert tests[0].code == "client_status"
    assert tests[0].featured is True
    assert "bhs" in codes
    assert "bdi" in codes
    assert "bai" in codes
    assert "schmischek" in codes
    assert "eyes" not in codes
    assert "wcq" in codes
    assert "osop" in codes
    assert "client_status" in codes


def test_bai_scoring_bands_and_interpretation_lead():
    from app.diagnostics.catalog import INTERPRETATION_LEAD_RU
    from app.diagnostics.engine import engine

    test = get_test("bai")
    assert test and test.runnable
    assert len(test.items) == 21
    # All mild (1) → total 21 → moderate (16–25) per BAI Manual 1993
    answers = {f"i{i}": 1 for i in range(1, 22)}
    result = engine.score("bai", answers)
    assert result["scores"]["total"] == 21
    assert result["scales"][0]["band_label"] == "умеренная"
    overall = result["interpretation"]["overall"]
    assert overall.startswith(INTERPRETATION_LEAD_RU[:40])
    assert "диагноз" in overall.lower()


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
    for code in ("client_status", "bhs", "bdi", "bai", "wcq", "schmischek", "osop"):
        test = get_test(code)
        assert test and test.runnable
        assert test.instruction
        assert any(ord(c) > 127 for c in test.instruction)


def test_runnable_and_pending():
    assert get_test("wcq") is not None
    assert get_test("wcq").runnable is True
    assert get_test("schmischek").runnable is True
    assert get_test("osop").runnable is True
    assert get_test("osop").requires_gender is True
    assert get_test("bhs").runnable is True
    assert get_test("bdi").runnable is True
    assert get_test("bai").runnable is True
    assert get_test("client_status").runnable is True
    assert get_test("eyes") is None


def test_osop_gender_variants():
    male = get_test("osop", gender="m")
    female = get_test("osop", gender="f")
    assert male and female
    assert len(male.items) == 97
    assert len(female.items) == 107
    answers_m = {item.id: 0 for item in male.items}
    answers_m["gender"] = "m"
    from app.diagnostics.engine import DiagnosticEngine

    result = DiagnosticEngine().score("osop", answers_m)
    assert result["scales"]
    assert result["interpretation"]["gender"] == "m"


def test_wcq_scoring_returns_eight_scales():
    from app.diagnostics.catalog import WCQ, score_wcq

    answers = {f"i{i}": 2 for i in range(1, 33)}
    result = score_wcq(answers, WCQ)
    assert len(result["scales"]) == 8
    assert "Профиль" in result["summary"]
    texts = {s["code"]: s["interpretation"] for s in result["scales"]}
    assert texts["confront"] != texts["escape"]
    assert "Конфронтация" in texts["confront"] or "конфронт" in texts["confront"].lower()


def test_interpretation_bands_cover_each_scale_without_gaps():
    from app.diagnostics.interpretations import iter_scale_bands

    max_by = {
        ("bai", "total"): 63,
        ("bdi", "total"): 63,
        ("bhs", "total"): 20,
        ("eyes", "accuracy"): 12,
    }
    for test_code, scale_code, bands in iter_scale_bands():
        assert bands, (test_code, scale_code)
        ordered = sorted(bands, key=lambda b: b[0])
        assert ordered[0][0] == 0
        for prev, cur in zip(ordered, ordered[1:]):
            assert prev[1] + 1 == cur[0], (test_code, scale_code, prev, cur)
        cap = max_by.get((test_code, scale_code))
        if cap is not None:
            assert ordered[-1][1] >= cap
        if test_code in ("wcq", "schmischek", "osop"):
            assert all(text.strip() for *_, text in bands)


def test_osop_scale_texts_are_scale_specific():
    from app.diagnostics.interpretations import band_for_score

    a = band_for_score("osop", "social_desirability", 2)
    b = band_for_score("osop", "self_harm", 2)
    assert a and b
    assert a[1] != b[1]


def test_bai_band_lookup_from_interpretations_file():
    from app.diagnostics.engine import engine
    from app.diagnostics.interpretations import band_for_score

    assert band_for_score("bai", "total", 0)[0] == "минимальная"
    assert band_for_score("bai", "total", 8)[0] == "лёгкая"
    assert band_for_score("bai", "total", 16)[0] == "умеренная"
    assert band_for_score("bai", "total", 26)[0] == "выраженная"
    answers = {f"i{i}": 0 for i in range(1, 22)}
    result = engine.score("bai", answers)
    assert result["scales"][0]["band_label"] == "минимальная"
    assert "диагноз" in result["interpretation"]["overall"].lower() or "предположительн" in result["interpretation"]["overall"].lower()


def _status_base_answers(**overrides):
    data = {
        "i1": "married",
        "i2": "partner",
        "i3": "7",
        "i4": "anxiety",
        "i5": "months",
        "i6": "talk",
        "i7": "one",
        "i8": "rather_good",
        "i9": "work",
        "i9b": "6",
        "i10": "rather_calm",
        "i11": "rather_safe",
        "i12": "close",
        "i13": "no",
        "i14": "no",
        "i16": "anxiety",
    }
    data.update(overrides)
    return data


def test_client_status_missing_skips_hidden_and_optional_notes():
    test = get_test("client_status")
    answers = _status_base_answers()
    assert missing_answer_ids(test, answers) == []
    answers["i13"] = "yes"
    assert missing_answer_ids(test, answers) == []
    answers["i14"] = "psychiatrist"
    missing = set(missing_answer_ids(test, answers))
    assert "i14b" in missing
    assert "i15" in missing
    answers["i14b"] = "partial"
    answers["i15"] = "current"
    answers["i15_note"] = ""
    assert missing_answer_ids(test, answers) == []


def test_client_status_scoring_keeps_readable_answers():
    from app.diagnostics.engine import engine
    from app.diagnostics.catalog import INTERPRETATION_LEAD_RU

    result = engine.score("client_status", _status_base_answers())
    assert result["interpretation"]["overall"].startswith(INTERPRETATION_LEAD_RU[:40])
    rows = result["interpretation"]["answers"]
    assert any(r["id"] == "i3" and r["answer"] == "7" for r in rows)
    assert any(r["id"] == "i4" and "Тревога" in r["answer"] for r in rows)
    assert not any(r["id"] == "i15" for r in rows)
    with_trauma = _status_base_answers(i13="yes", i13_note="кратко")
    rows2 = engine.score("client_status", with_trauma)["interpretation"]["answers"]
    trauma = next(r for r in rows2 if r["id"] == "i13")
    assert trauma["note"] == "кратко"


def test_client_status_slider_keeps_min_and_max():
    from app.diagnostics.engine import engine

    low = engine.score("client_status", _status_base_answers(i3="1", i9b="1"))
    high = engine.score("client_status", _status_base_answers(i3="10", i9b="10"))
    assert any(r["id"] == "i3" and r["answer"] == "1" for r in low["interpretation"]["answers"])
    assert any(r["id"] == "i9b" and r["answer"] == "1" for r in low["interpretation"]["answers"])
    assert any(r["id"] == "i3" and r["answer"] == "10" for r in high["interpretation"]["answers"])
    assert any(r["id"] == "i9b" and r["answer"] == "10" for r in high["interpretation"]["answers"])
    assert "1/10" in low["interpretation"]["overall"]
    assert "10/10" in high["interpretation"]["overall"]


def test_client_status_q13_no_omits_note():
    from app.diagnostics.engine import engine

    result = engine.score("client_status", _status_base_answers(i13="no", i13_note="не должно сохраниться как ответ"))
    rows = {r["id"]: r for r in result["interpretation"]["answers"]}
    assert rows["i13"]["answer"] == "Нет"
    assert not rows["i13"]["note"]
    assert "i15" not in rows


def test_parse_diagnostic_answers_accepts_notes():
    items = [
        ("i13", "yes"),
        ("i13_note", "текст"),
        ("i9b", "8"),
        ("csrf_token", "x"),
    ]
    parsed = parse_diagnostic_answers(items)
    assert parsed == {"i13": "yes", "i13_note": "текст", "i9b": "8"}
