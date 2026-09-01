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
    instruction: str = ""
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


def _score_likert_scales(
    answers: dict[str, Any],
    test: TestDefinition,
    *,
    item_scale_map: dict[str, str],
    scale_by_code: dict[str, ScaleDef],
) -> dict[str, Any]:
    totals: dict[str, int] = {code: 0 for code in scale_by_code}
    for item_id, scale_code in item_scale_map.items():
        raw = answers.get(item_id)
        if raw is None:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        totals[scale_code] = totals.get(scale_code, 0) + val

    scales_out = []
    for code, scale in scale_by_code.items():
        score = totals.get(code, 0)
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
    top = max(scales_out, key=lambda s: s["score"]) if scales_out else None
    summary = (
        f"{top['title']}: {top['score']}/{top['max']} ({top['band_label']})"
        if top
        else "Профиль по шкалам"
    )
    elevated = [s for s in scales_out if s["band_label"] in ("повышенная", "выраженная")]
    overall = (
        "Наиболее выражены: " + ", ".join(s["title"] for s in elevated)
        if elevated
        else "Профиль шкал в пределах умеренных значений по краткой форме."
    )
    return {
        "scores": totals,
        "scales": scales_out,
        "summary": summary,
        "interpretation": {"overall": overall, "disclaimer": DISCLAIMER_RU, "crisis_hint": ""},
        "flags": [],
    }


def _score_yes_no_scales(
    answers: dict[str, Any],
    test: TestDefinition,
    *,
    item_scale_map: dict[str, str],
    scale_by_code: dict[str, ScaleDef],
) -> dict[str, Any]:
    totals: dict[str, int] = {code: 0 for code in scale_by_code}
    for item_id, scale_code in item_scale_map.items():
        raw = answers.get(item_id)
        if raw is None:
            continue
        try:
            if int(raw) == 1:
                totals[scale_code] = totals.get(scale_code, 0) + 1
        except (TypeError, ValueError):
            continue

    scales_out = []
    for code, scale in scale_by_code.items():
        score = totals.get(code, 0)
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
    elevated = [s for s in scales_out if s["band_label"] in ("умеренная", "выраженная")]
    overall = (
        "Выраженные акцентуации: " + ", ".join(s["title"] for s in elevated)
        if elevated
        else "Ярко выраженных акцентуаций по краткой форме не выявлено."
    )
    top = max(scales_out, key=lambda s: s["score"]) if scales_out else None
    summary = (
        f"{top['title']}: {top['score']}/{top['max']} ({top['band_label']})"
        if top
        else "Профиль акцентуаций"
    )
    return {
        "scores": totals,
        "scales": scales_out,
        "summary": summary,
        "interpretation": {"overall": overall, "disclaimer": DISCLAIMER_RU, "crisis_hint": ""},
        "flags": [],
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
    title="Шкала безнадёжности Бека",
    short_description="20 утверждений о взгляде на будущее. Оценка уровня безнадёжности.",
    instruction=(
        "Прочитайте каждое утверждение. Отметьте «Верно», если оно в целом соответствует "
        "тому, как вы думаете и чувствуете в последнее время, и «Неверно» — если не соответствует. "
        "Отвечайте честно, правильных или неправильных ответов нет."
    ),
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
    "Оцените, насколько вас беспокоило плохое настроение и чувство грусти в последнюю неделю.",
    "Оцените, насколько вас беспокоил пессимизм и безнадёжное отношение к будущему в последнюю неделю.",
    "Оцените, насколько вас беспокоило чувство неудачи и несостоятельности в последнюю неделю.",
    "Оцените, насколько вас беспокоило отсутствие удовлетворённости жизнью в последнюю неделю.",
    "Оцените, насколько вас беспокоило чувство вины в последнюю неделю.",
    "Оцените, насколько вас беспокоило ожидание наказания в последнюю неделю.",
    "Оцените, насколько вас беспокоило негативное отношение к себе в последнюю неделю.",
    "Оцените, насколько вас беспокоила самокритика и самообвинение в последнюю неделю.",
    "Оцените, насколько вас беспокоили мысли о смерти или причинении себе вреда в последнюю неделю.",
    "Оцените, насколько вас беспокоили слёзы и плач в последнюю неделю.",
    "Оцените, насколько вас беспокоила раздражительность в последнюю неделю.",
    "Оцените, насколько вас беспокоило снижение интереса к людям и общению в последнюю неделю.",
    "Оцените, насколько вас беспокоили трудности с принятием решений в последнюю неделю.",
    "Оцените, насколько вас беспокоило негативное восприятие своей внешности в последнюю неделю.",
    "Оцените, насколько вас беспокоило снижение работоспособности в последнюю неделю.",
    "Оцените, насколько вас беспокоили нарушения сна в последнюю неделю.",
    "Оцените, насколько вас беспокоила повышенная утомляемость в последнюю неделю.",
    "Оцените, насколько вас беспокоили изменения аппетита в последнюю неделю.",
    "Оцените, насколько вас беспокоило изменение веса в последнюю неделю.",
    "Оцените, насколько вас беспокоило беспокойство о своём здоровье в последнюю неделю.",
    "Оцените, насколько вас беспокоило снижение интереса к сексуальной жизни в последнюю неделю.",
]


def _bdi_items() -> tuple[ItemDef, ...]:
    opts = (
        ("совсем не беспокоило", 0),
        ("слегка беспокоило", 1),
        ("умеренно беспокоило", 2),
        ("сильно беспокоило", 3),
    )
    return tuple(
        ItemDef(id=f"i{i}", text=stem, options=opts, scale_code="total")
        for i, stem in enumerate(_BDI_STEMS, start=1)
    )


BDI = TestDefinition(
    code="bdi",
    version="1-classic",
    title="Шкала депрессии Бека",
    short_description="21 вопрос об эмоциональном состоянии за последнюю неделю.",
    instruction=(
        "Оцените каждый пункт по тому, насколько он вас беспокоил в последнюю неделю "
        "(включая сегодня). Выберите один из четырёх вариантов ответа под каждым вопросом."
    ),
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


# ── WCQ coping (краткая форма, 32 пункта, 8 шкал) ───────────────────────────

_WCQ_OPTS = (
    ("Совсем не характерно", 0),
    ("Слабо характерно", 1),
    ("Умеренно характерно", 2),
    ("Очень характерно", 3),
)
_WCQ_SCALE_BANDS = (
    (0, 3, "низкая", "Редко используется этот способ совладания."),
    (4, 6, "умеренная", "Иногда используется."),
    (7, 9, "повышенная", "Часто используется."),
    (10, 12, "выраженная", "Очень часто используется как основной способ."),
)
_WCQ_SCALES = {
    "confront": ScaleDef("confront", "Конфронтация", 0, 12, _WCQ_SCALE_BANDS),
    "distance": ScaleDef("distance", "Дистанцирование", 0, 12, _WCQ_SCALE_BANDS),
    "control": ScaleDef("control", "Самоконтроль", 0, 12, _WCQ_SCALE_BANDS),
    "support": ScaleDef("support", "Поиск поддержки", 0, 12, _WCQ_SCALE_BANDS),
    "accept": ScaleDef("accept", "Принятие ответственности", 0, 12, _WCQ_SCALE_BANDS),
    "escape": ScaleDef("escape", "Избегание", 0, 12, _WCQ_SCALE_BANDS),
    "plan": ScaleDef("plan", "Планирование", 0, 12, _WCQ_SCALE_BANDS),
    "reappraise": ScaleDef("reappraise", "Переоценка", 0, 12, _WCQ_SCALE_BANDS),
}
_WCQ_ITEMS_DATA: tuple[tuple[str, str], ...] = (
    ("confront", "Я стараюсь отстаивать свою позицию, даже если это вызывает спор."),
    ("confront", "Я говорю людям, что они должны изменить своё поведение."),
    ("confront", "Я настаиваю на том, чтобы мои права соблюдались."),
    ("confront", "Я выражаю недовольство напрямую."),
    ("distance", "Я стараюсь не принимать ситуацию слишком близко к сердцу."),
    ("distance", "Я отшучиваюсь, чтобы снизить напряжение."),
    ("distance", "Я делаю вид, что проблема не так важна."),
    ("distance", "Я отвлекаюсь на другие дела."),
    ("control", "Я стараюсь держать эмоции под контролем."),
    ("control", "Я не показываю другим, что переживаю."),
    ("control", "Я сдерживаю импульсивные реакции."),
    ("control", "Я действую спокойно и сдержанно."),
    ("support", "Я ищу поддержки у близких."),
    ("support", "Я прошу совета у людей, которым доверяю."),
    ("support", "Я делюсь переживаниями с друзьями или родными."),
    ("support", "Я обращаюсь за эмоциональной помощью."),
    ("accept", "Я признаю свою роль в сложившейся ситуации."),
    ("accept", "Я стараюсь понять, что мог сделать иначе."),
    ("accept", "Я беру ответственность за свои решения."),
    ("accept", "Я анализирую свои ошибки."),
    ("escape", "Я откладываю решение проблемы."),
    ("escape", "Я ухожу от неприятных мыслей."),
    ("escape", "Я избегаю людей и мест, связанных со стрессом."),
    ("escape", "Я занимаюсь чем-то, чтобы не думать о проблеме."),
    ("plan", "Я составляю план действий."),
    ("plan", "Я ищу информацию, чтобы лучше понять ситуацию."),
    ("plan", "Я перечисляю возможные варианты решения."),
    ("plan", "Я действую шаг за шагом."),
    ("reappraise", "Я ищу смысл в происходящем."),
    ("reappraise", "Я стараюсь увидеть положительные стороны."),
    ("reappraise", "Я напоминаю себе, что трудности временны."),
    ("reappraise", "Я переосмысливаю ситуацию в более конструктивном ключе."),
)


def _wcq_items() -> tuple[ItemDef, ...]:
    items = []
    for idx, (scale_code, text) in enumerate(_WCQ_ITEMS_DATA, start=1):
        items.append(ItemDef(id=f"i{idx}", text=text, options=_WCQ_OPTS, scale_code=scale_code))
    return tuple(items)


def _wcq_item_map() -> dict[str, str]:
    return {f"i{i}": scale for i, (scale, _) in enumerate(_WCQ_ITEMS_DATA, start=1)}


def score_wcq(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    result = _score_likert_scales(
        answers, test, item_scale_map=_wcq_item_map(), scale_by_code=_WCQ_SCALES
    )
    result["summary"] = "Профиль способов совладания со стрессом"
    return result


WCQ = TestDefinition(
    code="wcq",
    version="1-short",
    title="Способы совладания со стрессом",
    short_description="32 утверждения, 8 шкал. Профиль стратегий совладания.",
    instruction=(
        "Прочитайте каждое утверждение и оцените, насколько описанный способ поведения "
        "характерен для вас в трудных или стрессовых ситуациях. Выберите один вариант под каждым пунктом."
    ),
    duration_minutes=12,
    source_citation="Folkman S., Lazarus R.S. Ways of Coping Questionnaire. Краткая адаптация для онлайн-скрининга.",
    source_urls=("https://psytests.org/coping/wcq.html",),
    scoring_status="ready",
    items=_wcq_items(),
    scales=tuple(_WCQ_SCALES.values()),
    score_fn=score_wcq,
    viz="radar",
)


# ── Schmischek accentuations (краткая форма, 40 пунктов) ───────────────────

_SHMI_SCALE_BANDS = (
    (0, 1, "низкая", "Акцентуация не выражена."),
    (2, 2, "умеренная", "Умеренная выраженность черты."),
    (3, 4, "выраженная", "Выраженная акцентуация — обсудите с психологом."),
)
_SHMI_SCALES = {
    "demo": ScaleDef("demo", "Демонстративность", 0, 4, _SHMI_SCALE_BANDS),
    "ped": ScaleDef("ped", "Педантичность", 0, 4, _SHMI_SCALE_BANDS),
    "stuck": ScaleDef("stuck", "Застревание", 0, 4, _SHMI_SCALE_BANDS),
    "excit": ScaleDef("excit", "Возбудимость", 0, 4, _SHMI_SCALE_BANDS),
    "hyper": ScaleDef("hyper", "Гипертимность", 0, 4, _SHMI_SCALE_BANDS),
    "dyst": ScaleDef("dyst", "Дистимность", 0, 4, _SHMI_SCALE_BANDS),
    "anx": ScaleDef("anx", "Тревожность", 0, 4, _SHMI_SCALE_BANDS),
    "cycl": ScaleDef("cycl", "Циклотимность", 0, 4, _SHMI_SCALE_BANDS),
    "emot": ScaleDef("emot", "Эмотивность", 0, 4, _SHMI_SCALE_BANDS),
    "exalt": ScaleDef("exalt", "Экзальтированность", 0, 4, _SHMI_SCALE_BANDS),
}
_SHMI_ITEMS_DATA: tuple[tuple[str, str], ...] = (
    ("demo", "Мне нравится быть в центре внимания."),
    ("demo", "Я легко заводлю новые знакомства."),
    ("demo", "Я люблю производить впечатление на других."),
    ("demo", "Я эмоционально выразителен(на) в общении."),
    ("ped", "Я люблю порядок и систему во всём."),
    ("ped", "Мне важно, чтобы всё было заранее спланировано."),
    ("ped", "Я переживаю, если нарушаются правила."),
    ("ped", "Я скрупулёзен(на) в деталях."),
    ("stuck", "Мне трудно отпускать обиды."),
    ("stuck", "Я долго переживаю неприятные события."),
    ("stuck", "Мне сложно простить людей."),
    ("stuck", "Я часто возвращаюсь мыслями к прошлому."),
    ("excit", "Я быстро выхожу из себя."),
    ("excit", "Мои реакции могут быть резкими."),
    ("excit", "Меня легко вывести из равновесия."),
    ("excit", "Я импульсивен(на) в поступках."),
    ("hyper", "Я энергичен(на) и оптимистичен(на)."),
    ("hyper", "Мне нравится активный ритм жизни."),
    ("hyper", "Я легко загораюсь новыми идеями."),
    ("hyper", "У меня много планов и интересов."),
    ("dyst", "Я склонен(на) к пониженному настроению."),
    ("dyst", "Мне часто кажется, что всё безрадостно."),
    ("dyst", "Я пессимистично смотрю на будущее."),
    ("dyst", "Мне трудно радоваться простым вещам."),
    ("anx", "Я часто беспокоюсь о будущем."),
    ("anx", "Мне свойственны сомнения и тревожные мысли."),
    ("anx", "Я легко пугаюсь неожиданностей."),
    ("anx", "Мне трудно расслабиться."),
    ("cycl", "Моё настроение заметно меняется."),
    ("cycl", "Бывают периоды подъёма и спада сил."),
    ("cycl", "Моя работоспособность нестабильна."),
    ("cycl", "Эмоции то приходят, то уходят."),
    ("emot", "Я глубоко переживаю события."),
    ("emot", "Мне свойственна эмоциональная чувствительность."),
    ("emot", "Я сопереживаю другим людям."),
    ("emot", "Чужая боль вызывает у меня сильный отклик."),
    ("exalt", "Я ярко реагирую на события."),
    ("exalt", "Мои эмоции могут быть бурными."),
    ("exalt", "Меня легко вдохновить или расстроить."),
    ("exalt", "Я склонен(на) к восторгам и разочарованиям."),
)


def _shmi_items() -> tuple[ItemDef, ...]:
    return tuple(
        ItemDef(
            id=f"i{i}",
            text=text,
            options=(("Да, характерно", 1), ("Нет, не характерно", 0)),
            scale_code=scale,
        )
        for i, (scale, text) in enumerate(_SHMI_ITEMS_DATA, start=1)
    )


def _shmi_item_map() -> dict[str, str]:
    return {f"i{i}": scale for i, (scale, _) in enumerate(_SHMI_ITEMS_DATA, start=1)}


def score_schmischek(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    return _score_yes_no_scales(
        answers, test, item_scale_map=_shmi_item_map(), scale_by_code=_SHMI_SCALES
    )


SCHMISCHEK = TestDefinition(
    code="schmischek",
    version="1-short",
    title="Акцентуации характера",
    short_description="40 утверждений, 10 шкал акцентуаций.",
    instruction=(
        "Прочитайте каждое утверждение о чертах характера. Отметьте «Да, характерно», "
        "если это в целом про вас, и «Нет, не характерно» — если не про вас."
    ),
    duration_minutes=15,
    source_citation="Leonhard K. / Schmischek accentuation questionnaire. Краткая адаптация для скрининга.",
    source_urls=("https://psytests.org/accent/shmi90acc.html",),
    scoring_status="ready",
    items=_shmi_items(),
    scales=tuple(_SHMI_SCALES.values()),
    score_fn=score_schmischek,
    viz="radar",
)


# ── OSOP parenting attitudes (краткая форма) ────────────────────────────────

_OSOP_OPTS = (
    ("Полностью не согласен", 1),
    ("Скорее не согласен", 2),
    ("Нейтрально", 3),
    ("Скорее согласен", 4),
    ("Полностью согласен", 5),
)
_OSOP_SCALE_BANDS = (
    (4, 8, "низкая", "Стиль выражен слабо."),
    (9, 14, "умеренная", "Умеренная выраженность стиля."),
    (15, 20, "выраженная", "Стиль выражен ярко."),
)
_OSOP_SCALES = {
    "authoritarian": ScaleDef("authoritarian", "Авторитарность", 4, 20, _OSOP_SCALE_BANDS),
    "democratic": ScaleDef("democratic", "Демократичность", 4, 20, _OSOP_SCALE_BANDS),
    "permissive": ScaleDef("permissive", "Попустительство", 4, 20, _OSOP_SCALE_BANDS),
}
_OSOP_ITEMS_DATA: tuple[tuple[str, str], ...] = (
    ("authoritarian", "Ребёнок должен безусловно подчиняться взрослым."),
    ("authoritarian", "Нарушение правил должно наказываться."),
    ("authoritarian", "Родитель всегда прав в споре с ребёнком."),
    ("authoritarian", "Дисциплина важнее эмоций ребёнка."),
    ("authoritarian", "Ребёнку нельзя оспаривать мои решения."),
    ("authoritarian", "Я строго контролирую поведение ребёнка."),
    ("democratic", "Важно объяснять ребёнку причины правил."),
    ("democratic", "Я учитываю мнение ребёнка при решениях."),
    ("democratic", "Мы обсуждаем семейные правила вместе."),
    ("democratic", "Ребёнок может высказывать свои чувства."),
    ("democratic", "Я поддерживаю самостоятельность ребёнка."),
    ("democratic", "Я поощряю ответственность, а не только послушание."),
    ("permissive", "Я часто иду на уступки, чтобы избежать конфликта."),
    ("permissive", "Мне трудно отказывать ребёнку."),
    ("permissive", "Правила у нас часто меняются."),
    ("permissive", "Я редко наказываю за проступки."),
    ("permissive", "Ребёнок сам решает, чем заниматься."),
    ("permissive", "Я избегаю строгих требований."),
)


def _osop_items() -> tuple[ItemDef, ...]:
    return tuple(
        ItemDef(id=f"i{i}", text=text, options=_OSOP_OPTS, scale_code=scale)
        for i, (scale, text) in enumerate(_OSOP_ITEMS_DATA, start=1)
    )


def _osop_item_map() -> dict[str, str]:
    return {f"i{i}": scale for i, (scale, _) in enumerate(_OSOP_ITEMS_DATA, start=1)}


def score_osop(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    return _score_likert_scales(
        answers, test, item_scale_map=_osop_item_map(), scale_by_code=_OSOP_SCALES
    )


OSOP = TestDefinition(
    code="osop",
    version="1-short",
    title="Стили семейного воспитания",
    short_description="18 утверждений о родительских установках, 3 шкалы.",
    instruction=(
        "Прочитайте каждое утверждение о воспитании и отметьте степень своего согласия. "
        "Отвечайте так, как это обычно бывает у вас в отношениях с ребёнком."
    ),
    duration_minutes=10,
    source_citation="OSOP / parenting style inventories. Краткая адаптация для онлайн-опроса.",
    source_urls=("https://psytests.org/parent/osopFf.html",),
    scoring_status="ready",
    items=_osop_items(),
    scales=tuple(_OSOP_SCALES.values()),
    score_fn=score_osop,
    viz="radar",
)


# Pending tests — catalog only until assets/keys are supplied.
PENDING_TESTS = (
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
)

_REGISTRY: dict[str, TestDefinition] = {
    BHS.code: BHS,
    BDI.code: BDI,
    WCQ.code: WCQ,
    SCHMISCHEK.code: SCHMISCHEK,
    OSOP.code: OSOP,
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
