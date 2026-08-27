"""Versioned diagnostic test definitions and scoring plugins.

Only tests with verified scoring keys are marked runnable.
Item banks cite published adaptations; operators must ensure licensing for production use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


DISCLAIMER_RU = (
    "Результат опросника не является медицинским диагнозом и не заменяет "
    "очную консультацию психолога или врача. При ухудшении состояния обратитесь "
    "за профессиональной помощью."
)

CRISIS_HINT_RU = (
    "Если вам очень тяжело или есть мысли о самоповреждении, обратитесь "
    "за срочной помощью: экстренные службы 112 / 103, или телефон доверия в вашем регионе."
)


@dataclass(frozen=True)
class ScaleDef:
    code: str
    title: str
    min_score: int
    max_score: int
    bands: tuple[tuple[int, int, str, str], ...]  # lo, hi, label, interpretation


@dataclass(frozen=True)
class ItemDef:
    id: str
    text: str
    options: tuple[tuple[str, int], ...]  # value label → score contribution
    reverse: bool = False
    scale_code: str = "total"


@dataclass
class TestDefinition:
    code: str
    version: str
    title: str
    short_description: str
    duration_minutes: int
    source_citation: str
    source_urls: tuple[str, ...]
    scoring_status: str  # ready | pending_source
    items: tuple[ItemDef, ...] = ()
    scales: tuple[ScaleDef, ...] = ()
    score_fn: Callable[[dict[str, Any], "TestDefinition"], dict[str, Any]] | None = None
    viz: str = "bars"  # bars | bands | radar
    attention_flags: tuple[str, ...] = ()

    @property
    def runnable(self) -> bool:
        return self.scoring_status == "ready" and bool(self.items) and self.score_fn is not None


def _band_for(score: int, scale: ScaleDef) -> tuple[str, str]:
    for lo, hi, label, text in scale.bands:
        if lo <= score <= hi:
            return label, text
    return "вне диапазона", "Значение вне описанных диапазонов методики."


def score_sum_total(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    """Generic sum of option scores for items (supports reverse)."""
    total = 0
    detail = []
    for item in test.items:
        raw = answers.get(item.id)
        if raw is None:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        score = val
        if item.reverse:
            opts = [o[1] for o in item.options]
            if opts:
                score = (min(opts) + max(opts)) - val
        total += score
        detail.append({"item_id": item.id, "raw": val, "score": score})

    scale = test.scales[0] if test.scales else ScaleDef(
        code="total", title="Итог", min_score=0, max_score=total, bands=((0, total, "результат", ""),)
    )
    label, interp = _band_for(total, scale)
    flags: list[str] = []
    if "crisis_high" in test.attention_flags and total >= scale.bands[-1][0]:
        flags.append("attention_high")
    return {
        "scores": {"total": total},
        "scales": [
            {
                "code": scale.code,
                "title": scale.title,
                "score": total,
                "min": scale.min_score,
                "max": scale.max_score,
                "band_label": label,
                "interpretation": interp,
            }
        ],
        "summary": f"{scale.title}: {total} ({label})",
        "interpretation": {
            "overall": interp,
            "disclaimer": DISCLAIMER_RU,
            "crisis_hint": CRISIS_HINT_RU if flags else "",
        },
        "flags": flags,
        "answer_detail": detail,
    }


# ── Beck Hopelessness Scale (BHS) ──────────────────────────────────────────
# Structure: 20 true/false items; keyed true/false per Beck (1974).
# Cutoffs commonly cited in clinical literature (Beck & Steer):
# 0–3 minimal, 4–8 mild, 9–14 moderate, 15–20 severe.
# Russian educational adaptations follow the same keying.
# Item wording: Russian educational paraphrase set (not a licensed Pearson pack).

_BHS_TRUE_KEYS = {
    # items keyed True = hopelessness when answered True (1-based classic keys)
    2, 4, 7, 9, 11, 12, 14, 16, 17, 18, 20
}
_BHS_FALSE_KEYS = {1, 3, 5, 6, 8, 10, 13, 15, 19}

_BHS_ITEMS_RU = [
    "Я смотрю в будущее с надеждой и энтузиазмом.",
    "Мне лучше сдаться, потому что я ничего не могу изменить к лучшему.",
    "Когда дела идут плохо, меня утешает мысль, что так не может продолжаться вечно.",
    "Я не могу представить, какой будет моя жизнь через 10 лет.",
    "У меня достаточно времени, чтобы осуществить то, что я больше всего хочу.",
    "В будущем я рассчитываю добиться успеха в том, что мне больше всего важно.",
    "Моё будущее кажется мне тёмным.",
    "Я рассчитываю получить в жизни больше хорошего, чем средний человек.",
    "У меня просто нет удачи, и нет причин верить, что она появится в будущем.",
    "Мой прошлый опыт хорошо подготовил меня к будущему.",
    "Всё, что я вижу впереди — скорее неприятности, чем радости.",
    "Я не рассчитываю получить то, чего действительно хочу.",
    "Когда я смотрю в будущее, я ожидаю быть счастливее, чем сейчас.",
    "Дела складываются не так, как я хочу.",
    "Я очень верю в своё будущее.",
    "Я никогда не получу того, чего хочу, поэтому глупо чего-то хотеть.",
    "Маловероятно, что я получу реальное удовлетворение в будущем.",
    "Будущее кажется мне неопределённым и неясным.",
    "В будущем меня ждут больше хороших времён, чем плохих.",
    "Бесполезно стараться получить то, чего я хочу, потому что, вероятно, я этого не получу.",
]


def _bhs_items() -> tuple[ItemDef, ...]:
    items = []
    for i, text in enumerate(_BHS_ITEMS_RU, start=1):
        # options: True=1, False=0 stored; scoring applies keys
        items.append(
            ItemDef(
                id=f"i{i}",
                text=text,
                options=(("Верно", 1), ("Неверно", 0)),
                scale_code="total",
            )
        )
    return tuple(items)


def score_bhs(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    total = 0
    detail = []
    for i in range(1, 21):
        raw = answers.get(f"i{i}")
        if raw is None:
            continue
        try:
            answered_true = int(raw) == 1
        except (TypeError, ValueError):
            continue
        keyed = False
        if i in _BHS_TRUE_KEYS and answered_true:
            keyed = True
        if i in _BHS_FALSE_KEYS and not answered_true:
            keyed = True
        if keyed:
            total += 1
        detail.append({"item_id": f"i{i}", "answered_true": answered_true, "keyed": keyed})
    scale = test.scales[0]
    label, interp = _band_for(total, scale)
    flags = []
    if total >= 15:
        flags.append("attention_high")
    return {
        "scores": {"total": total},
        "scales": [
            {
                "code": "total",
                "title": scale.title,
                "score": total,
                "min": 0,
                "max": 20,
                "band_label": label,
                "interpretation": interp,
            }
        ],
        "summary": f"Безнадёжность: {total}/20 ({label})",
        "interpretation": {
            "overall": interp,
            "disclaimer": DISCLAIMER_RU,
            "crisis_hint": CRISIS_HINT_RU if total >= 9 else "",
        },
        "flags": flags,
        "answer_detail": detail,
    }


BHS = TestDefinition(
    code="bhs",
    version="1",
    title="Шкала безнадёжности Бека (BHS)",
    short_description="20 утверждений о взгляде на будущее. Оценка уровня безнадёжности.",
    duration_minutes=8,
    source_citation=(
        "Beck A.T. et al. (1974). The measurement of pessimism: The Hopelessness Scale. "
        "J Consult Clin Psychol. Cutoffs: Beck & Steer manuals / clinical literature "
        "(0–3 / 4–8 / 9–14 / 15–20). Russian educational adaptations use the same keys."
    ),
    source_urls=("https://psytests.org/depr/bhi-run.html",),
    scoring_status="ready",
    items=_bhs_items(),
    scales=(
        ScaleDef(
            code="total",
            title="Безнадёжность",
            min_score=0,
            max_score=20,
            bands=(
                (0, 3, "минимальная", "Показатель в диапазоне минимальной безнадёжности."),
                (4, 8, "лёгкая", "Лёгкая выраженность безнадёжности."),
                (9, 14, "умеренная", "Умеренная безнадёжность — имеет смысл обсудить с психологом."),
                (15, 20, "выраженная", "Высокий показатель безнадёжности. Рекомендуется обратиться за профессиональной поддержкой."),
            ),
        ),
    ),
    score_fn=score_bhs,
    viz="bands",
    attention_flags=("crisis_high",),
)


# ── Beck Depression Inventory (BDI) classic 21-item structure ──────────────
# Scoring: sum 0–63. Common bands (Beck et al.): 0–9 minimal, 10–18 mild,
# 19–29 moderate, 30–63 severe (classic BDI; BDI-II cutoffs differ).
# We use classic BDI bands and label version clearly.
# Items: condensed Russian educational stems (operator should replace with licensed text if required).

_BDI_STEMS = [
    "Настроение / грусть",
    "Пессимизм / будущее",
    "Ощущение неудачи",
    "Удовлетворённость жизнью",
    "Чувство вины",
    "Ожидание наказания",
    "Самоотношение",
    "Самокритика",
    "Суицидальные мысли",
    "Плач",
    "Раздражительность",
    "Интерес к людям",
    "Принятие решений",
    "Внешность / самооценка тела",
    "Работоспособность",
    "Сон",
    "Утомляемость",
    "Аппетит",
    "Вес",
    "Беспокойство о здоровье",
    "Интерес к сексу",
]


def _bdi_items() -> tuple[ItemDef, ...]:
    opts = (
        ("0 — отсутствует / редко", 0),
        ("1 — слабо выражено", 1),
        ("2 — умеренно выражено", 2),
        ("3 — сильно выражено", 3),
    )
    return tuple(
        ItemDef(id=f"i{i}", text=stem, options=opts, scale_code="total")
        for i, stem in enumerate(_BDI_STEMS, start=1)
    )


BDI = TestDefinition(
    code="bdi",
    version="1-classic",
    title="Шкала депрессии Бека (BDI)",
    short_description="21 тема, оценка выраженности депрессивной симптоматики за период.",
    duration_minutes=12,
    source_citation=(
        "Beck A.T. et al. Depression inventory. Classic BDI total 0–63; "
        "bands often cited: 0–9 minimal, 10–18 mild, 19–29 moderate, 30–63 severe. "
        "Item stems here are condensed thematic prompts for product MVP — "
        "replace with a licensed full-text pack for clinical use."
    ),
    source_urls=("https://psytests.org/depr/bdi.html",),
    scoring_status="ready",
    items=_bdi_items(),
    scales=(
        ScaleDef(
            code="total",
            title="Депрессия (BDI)",
            min_score=0,
            max_score=63,
            bands=(
                (0, 9, "минимальная", "Суммарный балл в диапазоне минимальной выраженности."),
                (10, 18, "лёгкая", "Лёгкая выраженность симптомов по шкале BDI."),
                (19, 29, "умеренная", "Умеренная выраженность — рекомендуется обсуждение со специалистом."),
                (30, 63, "выраженная", "Высокий суммарный балл. Рекомендуется обратиться за профессиональной помощью."),
            ),
        ),
    ),
    score_fn=score_sum_total,
    viz="bands",
    attention_flags=("crisis_high",),
)


# Pending tests — catalog only until verified full keys + licensed items are supplied.
PENDING_TESTS = (
    TestDefinition(
        code="schmischek",
        version="0",
        title="Акцентуации характера (Шмишек)",
        short_description="Опросник акцентуаций. Расчёт шкал будет подключён после верификации ключей.",
        duration_minutes=20,
        source_citation="Leonhard / Schmischek adaptations — keys pending verification.",
        source_urls=("https://psytests.org/accent/shmi90acc.html",),
        scoring_status="pending_source",
    ),
    TestDefinition(
        code="rmet",
        version="0",
        title="Чтение эмоций по глазам (RMET)",
        short_description="Требует набора изображений и ключей Baron-Cohen. Пока в каталоге.",
        duration_minutes=15,
        source_citation="Baron-Cohen S. et al. Reading the Mind in the Eyes — assets/keys pending.",
        source_urls=("https://psytests.org/emo/eyespsy.html",),
        scoring_status="pending_source",
    ),
    TestDefinition(
        code="wcq",
        version="0",
        title="Опросник способов совладания (WCQ)",
        short_description="Folkman & Lazarus WCQ — шкалы и reverse-пункты pending.",
        duration_minutes=15,
        source_citation="Folkman S., Lazarus R.S. Ways of Coping Questionnaire — keys pending.",
        source_urls=("https://psytests.org/coping/wcq.html",),
        scoring_status="pending_source",
    ),
    TestDefinition(
        code="osop",
        version="0",
        title="Стили семейного воспитания / отношение родителей",
        short_description="Методика OSOP — ключи и нормы pending.",
        duration_minutes=20,
        source_citation="OSOP / parenting style inventories — keys pending verification.",
        source_urls=("https://psytests.org/parent/osopFf.html",),
        scoring_status="pending_source",
    ),
)

_REGISTRY: dict[str, TestDefinition] = {
    BHS.code: BHS,
    BDI.code: BDI,
}
for t in PENDING_TESTS:
    _REGISTRY[t.code] = t


def list_tests(*, only_runnable: bool = False) -> list[TestDefinition]:
    tests = list(_REGISTRY.values())
    if only_runnable:
        tests = [t for t in tests if t.runnable]
    return tests


def get_test(code: str) -> TestDefinition | None:
    return _REGISTRY.get((code or "").strip().lower())
