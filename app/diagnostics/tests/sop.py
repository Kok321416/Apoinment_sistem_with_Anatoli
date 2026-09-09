"""СОП (А. Н. Орел) — склонность к отклоняющемуся поведению, мужской/женский вариант.

Источник формулировок и структуры: публичные адаптации методики (см. psytests.org/parent/osopFf).
Коэффициенты коррекции по шкале лжи не применяются (как в онлайн-версии psytests).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.diagnostics.catalog import (
    CRISIS_HINT_RU,
    DISCLAIMER_RU,
    ItemDef,
    ScaleDef,
    TestDefinition,
    _band_for,
)

_YES_NO = (("Да", 1), ("Нет", 0))

_SCALE_META: dict[str, tuple[str, int]] = {
    "social_desirability": ("Установка на социально желательные ответы", 20),
    "norms": ("Склонность к нарушению норм и правил", 20),
    "addictive": ("Склонность к аддиктивному поведению", 25),
    "self_harm": ("Склонность к самоповреждающему поведению", 25),
    "aggression": ("Склонность к агрессии и насилию", 30),
    "volition": ("Волевой контроль эмоциональных реакций", 20),
    "delinquent": ("Склонность к делинквентному поведению", 25),
    "female_role": ("Принятие женской социальной роли", 35),
}

_BANDS = (
    (0, 4, "низкая", "Показатель в зоне низких значений для данной шкалы."),
    (5, 9, "умеренная", "Умеренная выраженность."),
    (10, 14, "повышенная", "Повышенные значения — обратить внимание специалиста."),
    (15, 99, "высокая", "Высокие значения по шкале."),
)


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    path = Path(__file__).with_name("sop_data.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _items_for(gender: str) -> tuple[ItemDef, ...]:
    key = "male_items" if gender == "m" else "female_items"
    raw = _data()[key]
    items = []
    for num in sorted(raw.keys(), key=lambda x: int(x)):
        items.append(
            ItemDef(id=f"i{num}", text=raw[num], options=_YES_NO, scale_code="sop")
        )
    return tuple(items)


def _scales_for(gender: str) -> tuple[ScaleDef, ...]:
    keys = _data()["male_keys" if gender == "m" else "female_keys"]
    out = []
    for code in keys:
        title, max_s = _SCALE_META.get(code, (code, 30))
        out.append(ScaleDef(code, title, 0, max_s, _BANDS))
    return tuple(out)


def _norm_gender(raw: Any) -> str:
    g = str(raw or "").strip().lower()
    if g in ("f", "female", "ж", "woman", "w"):
        return "f"
    return "m"


def score_sop(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    gender = _norm_gender(answers.get("gender") or getattr(test, "sop_gender", "m"))
    key_map = _data()["female_keys" if gender == "f" else "male_keys"]
    scale_defs = {s.code: s for s in _scales_for(gender)}
    scores: dict[str, int] = {code: 0 for code in key_map}
    for code, pairs in key_map.items():
        for num, yes_scores in pairs:
            raw = answers.get(f"i{num}")
            if raw is None:
                continue
            try:
                ans = int(raw)
            except (TypeError, ValueError):
                continue
            # ans: 1=Да, 0=Нет. yes_scores=1 means Да adds point; 0 means Нет adds point.
            if yes_scores and ans == 1:
                scores[code] += 1
            elif not yes_scores and ans == 0:
                scores[code] += 1

    scales_out = []
    for code, score in scores.items():
        scale = scale_defs[code]
        label, interp = _band_for(score, scale)
        scales_out.append(
            {
                "code": code,
                "title": scale.title,
                "score": score,
                "min": scale.min_score,
                "max": scale.max_score,
                "band_label": label,
                "interpretation": interp,
            }
        )
    top = sorted(scales_out, key=lambda s: s["score"], reverse=True)
    summary_bits = [f"{s['title']}: {s['score']} ({s['band_label']})" for s in top[:3]]
    flags = []
    for s in scales_out:
        if s["code"] in ("self_harm", "aggression", "delinquent") and s["score"] >= 10:
            flags.append(s["code"])
    interpretation = {
        "overall": "; ".join(summary_bits),
        "disclaimer": DISCLAIMER_RU,
        "crisis_hint": CRISIS_HINT_RU if flags else "",
        "gender": gender,
    }
    return {
        "scores": scores,
        "scales": scales_out,
        "summary": f"СОП ({'жен.' if gender == 'f' else 'муж.'}): " + "; ".join(summary_bits),
        "interpretation": interpretation,
        "flags": flags,
    }


def build_osop_test(gender: str | None = None) -> TestDefinition:
    """Return СОП definition; with gender set, items are gender-specific."""
    g_raw = (gender or "").strip().lower()
    if g_raw in ("f", "female", "ж", "w", "woman"):
        g = "f"
    elif g_raw in ("m", "male", "м", "man"):
        g = "m"
    else:
        g = ""

    base = TestDefinition(
        code="osop",
        version="orel-sop-1",
        title="Склонность к отклоняющемуся поведению (СОП)",
        short_description=(
            "Методика А. Н. Орла: сначала выберите вариант для женщин или мужчин, "
            "затем ответьте Да/Нет на утверждения."
        ),
        instruction=(
            "Перед вами ряд утверждений о сторонах жизни, характера и привычек. "
            "Прочитайте каждое и решите, верно ли оно по отношению к вам сейчас. "
            "Если затрудняетесь — выберите более подходящий вариант. "
            "Здесь нет плохих или хороших ответов; важна первая реакция."
        ),
        duration_minutes=25,
        source_citation="А. Н. Орел (1992). Определение склонности к отклоняющемуся поведению (СОП).",
        source_urls=(
            "https://psytests.org/parent/osopFf-run.html",
            "https://psytests.org/parent/osopFf.html",
        ),
        scoring_status="ready",
        items=_items_for(g) if g else (),
        scales=_scales_for(g or "m"),
        score_fn=score_sop,
        viz="bars",
        attention_flags=("self_harm", "aggression", "delinquent"),
        requires_gender=True,
    )
    base.sop_gender = g or None  # type: ignore[attr-defined]
    return base


# Catalog entry: listed as runnable; items appear after gender is chosen.
OSOP = build_osop_test(None)
