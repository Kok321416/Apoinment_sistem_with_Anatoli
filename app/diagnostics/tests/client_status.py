"""Client status / anamnesis questionnaire (not a clinical scale)."""
from __future__ import annotations

from typing import Any

from app.diagnostics.catalog import (
    DISCLAIMER_RU,
    ItemDef,
    TestDefinition,
    compose_overall_interpretation,
    item_is_visible,
)

CODE = "client_status"


def _o(*pairs: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    return pairs


def _single(item_id: str, text: str, options: tuple[tuple[str, str], ...], **kwargs: Any) -> ItemDef:
    return ItemDef(id=item_id, text=text, options=options, kind="single", **kwargs)


CLIENT_STATUS_ITEMS: tuple[ItemDef, ...] = (
    _single(
        "i1",
        "Как сейчас устроена ваша личная жизнь?",
        _o(
            ("В браке", "married"),
            ("В отношениях", "relationship"),
            ("Разведён(а)", "divorced"),
            ("Один/одна", "single"),
            ("Другое", "other"),
            ("Не хочу отвечать", "skip"),
        ),
        other_values=("other",),
        other_placeholder="Можете уточнить, если хотите",
    ),
    _single(
        "i2",
        "С кем вы живёте?",
        _o(
            ("Один/одна", "alone"),
            ("С партнёром", "partner"),
            ("С родителями", "parents"),
            ("С детьми", "children"),
            ("С родственниками", "relatives"),
            ("С друзьями", "friends"),
            ("С другими людьми", "others"),
        ),
    ),
    ItemDef(
        id="i3",
        text="Как вы оцениваете своё состояние сейчас?",
        kind="slider",
        min_value=1,
        max_value=10,
        slider_low="очень плохо",
        slider_high="очень хорошо",
    ),
    _single(
        "i4",
        "Что сейчас беспокоит больше всего?",
        _o(
            ("Тревога", "anxiety"),
            ("Настроение", "mood"),
            ("Отношения", "relations"),
            ("Работа", "work"),
            ("Семья", "family"),
            ("Самооценка", "self_esteem"),
            ("Сон", "sleep"),
            ("Другое", "other"),
        ),
        other_values=("other",),
        other_placeholder="Опишите, что именно, если хотите",
    ),
    _single(
        "i5",
        "Как давно вы чувствуете, что есть проблема?",
        _o(
            ("Несколько дней", "days"),
            ("Несколько недель", "weeks"),
            ("Несколько месяцев", "months"),
            ("Больше года", "year_plus"),
            ("Давно", "long"),
            ("Не знаю", "unknown"),
        ),
    ),
    _single(
        "i6",
        "Как вы обычно справляетесь со стрессом?",
        _o(
            ("Разговариваю", "talk"),
            ("Отдыхаю", "rest"),
            ("Спорт", "sport"),
            ("Работаю", "work"),
            ("Закрываюсь", "withdraw"),
            ("Алкоголь/другое", "substance"),
            ("По-разному", "mixed"),
            ("Мой вариант", "other"),
        ),
        other_values=("other",),
        other_placeholder="Ваш вариант, если хотите",
    ),
    _single(
        "i7",
        "Есть ли человек, к которому вы можете обратиться за поддержкой?",
        _o(
            ("Да, близкий", "one"),
            ("Да, несколько", "several"),
            ("Скорее нет", "rather_no"),
            ("Нет", "no"),
        ),
    ),
    _single(
        "i8",
        "Как сейчас складываются отношения с близкими?",
        _o(
            ("Хорошо", "good"),
            ("Скорее хорошо", "rather_good"),
            ("Напряжённо", "tense"),
            ("Конфликтно", "conflict"),
            ("Почти не общаемся", "distant"),
            ("Затрудняюсь ответить", "unsure"),
        ),
    ),
    _single(
        "i9",
        "Вы сейчас",
        _o(
            ("Работаете", "work"),
            ("Учитесь", "study"),
            ("Другое", "other"),
        ),
        slide_group="q9",
        other_values=("other",),
        other_placeholder="Укажите, если хотите",
    ),
    ItemDef(
        id="i9b",
        text="Насколько вас устраивает ваша работа, учёба, состояние жизни в данный момент?",
        kind="slider",
        min_value=1,
        max_value=10,
        slider_low="совсем не устраивает",
        slider_high="полностью устраивает",
        slide_group="q9",
    ),
    _single(
        "i10",
        "Каким было ваше детство в семье?",
        _o(
            ("Спокойным", "calm"),
            ("Скорее спокойным", "rather_calm"),
            ("Напряжённым", "tense"),
            ("Конфликтным", "conflict"),
            ("Очень сложным", "very_hard"),
            ("Не хочу отвечать", "skip"),
        ),
    ),
    _single(
        "i11",
        "Как вы чувствовали себя в семье в детстве?",
        _o(
            ("В безопасности", "safe"),
            ("Скорее в безопасности", "rather_safe"),
            ("Часто тревожно", "anxious"),
            ("Часто одиноко", "lonely"),
            ("Меня часто критиковали", "criticized"),
            ("Другое", "other"),
            ("Не хочу отвечать", "skip"),
        ),
        other_values=("other",),
        other_placeholder="Можете уточнить, если хотите",
    ),
    _single(
        "i12",
        "Насколько вы были близки с родителями / значимыми взрослыми?",
        _o(
            ("Очень близки", "very_close"),
            ("Скорее близки", "close"),
            ("По-разному", "mixed"),
            ("Скорее отдалённо", "distant"),
            ("Очень отдалённо", "very_distant"),
            ("Не хочу отвечать", "skip"),
            ("Другое", "other"),
        ),
        other_values=("other",),
        other_placeholder="Можете уточнить, если хотите",
    ),
    _single(
        "i13",
        "Были ли в детстве события, которые сильно на вас повлияли?",
        _o(
            ("Нет", "no"),
            ("Возможно", "maybe"),
            ("Да", "yes"),
            ("Не хочу отвечать", "skip"),
        ),
        other_values=("yes",),
        other_placeholder="Если хотите, можете кратко рассказать.",
    ),
    _single(
        "i14",
        "Обращались ли вы раньше за психологической/психиатрической помощью?",
        _o(
            ("Нет", "no"),
            ("Да, к психологу", "psychologist"),
            ("Да, к психиатру", "psychiatrist"),
            ("К обоим", "both"),
            ("Не хочу отвечать", "skip"),
        ),
    ),
    _single(
        "i14b",
        "Помощь была полезной?",
        _o(
            ("Да", "yes"),
            ("Частично", "partial"),
            ("Нет", "no"),
            ("Не знаю", "unknown"),
        ),
        show_if_item="i14",
        show_if_values=("psychologist", "psychiatrist", "both"),
    ),
    _single(
        "i15",
        "Вы принимали таблетки, которые назначал психиатр/невролог?",
        _o(
            ("Да", "yes"),
            ("Нет", "no"),
            ("Принимаю сейчас", "current"),
            ("Не хочу отвечать", "skip"),
            ("Другое", "other"),
        ),
        show_if_item="i14",
        show_if_values=("psychiatrist", "both"),
        other_values=("current", "other"),
        other_placeholder="Какие препараты — если хотите указать",
    ),
    _single(
        "i16",
        "Что вы хотели бы изменить в результате работы?",
        _o(
            ("Стать спокойнее", "calmer"),
            ("Улучшить отношения", "relations"),
            ("Лучше понимать себя", "self"),
            ("Повысить самооценку", "esteem"),
            ("Справиться с тревогой", "anxiety"),
            ("Улучшить настроение", "mood"),
            ("Решить конкретную проблему", "specific"),
            ("Другое", "other"),
        ),
        other_values=("other",),
        other_placeholder="Можете описать, если хотите",
    ),
)


def option_label(item: ItemDef, value: Any) -> str:
    if value is None or value == "":
        return ""
    if item.kind == "slider":
        return str(value)
    for label, val in item.options:
        if str(val) == str(value):
            return label
    return str(value)


def _note(answers: dict[str, Any], item_id: str) -> str:
    raw = answers.get(f"{item_id}_note")
    return str(raw).strip() if raw is not None else ""


def score_client_status(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in test.items:
        if not item_is_visible(item, answers):
            continue
        value = answers.get(item.id)
        note = _note(answers, item.id)
        if item.other_values and str(value or "") not in {str(v) for v in item.other_values}:
            note = ""
        if (value is None or value == "") and not note:
            continue
        rows.append(
            {
                "id": item.id,
                "question": item.text,
                "value": "" if value is None else str(value),
                "answer": option_label(item, value),
                "note": note,
            }
        )

    mood = answers.get("i3")
    try:
        mood_n = int(mood) if mood not in (None, "") else None
    except (TypeError, ValueError):
        mood_n = None
    concern = option_label(next(i for i in test.items if i.id == "i4"), answers.get("i4"))
    duration = option_label(next(i for i in test.items if i.id == "i5"), answers.get("i5"))
    support = option_label(next(i for i in test.items if i.id == "i7"), answers.get("i7"))
    goal = option_label(next(i for i in test.items if i.id == "i16"), answers.get("i16"))
    bits = []
    if mood_n is not None:
        bits.append(f"состояние сейчас {mood_n}/10")
    if concern:
        bits.append(f"больше всего беспокоит: {concern}")
    if duration:
        bits.append(f"давность: {duration}")
    if support:
        bits.append(f"поддержка: {support}")
    if goal:
        bits.append(f"запрос: {goal}")
    body = "Краткое резюме опроса: " + "; ".join(bits) + "." if bits else "Опрос о текущем состоянии заполнен."
    summary = "Опрос статуса: " + (f"состояние {mood_n}/10" if mood_n is not None else "ответы сохранены")
    return {
        "scores": {"mood": mood_n if mood_n is not None else 0},
        "scales": [],
        "summary": summary[:2000],
        "interpretation": {
            "overall": compose_overall_interpretation(body),
            "disclaimer": DISCLAIMER_RU,
            "crisis_hint": "",
            "answers": rows,
        },
        "flags": [],
    }


CLIENT_STATUS = TestDefinition(
    code=CODE,
    version="1",
    title="Общий опрос по статусу",
    short_description=(
        "Короткий опрос о текущей жизни и запросе — не тест и не диагноз. "
        "Лучше пройти первым: ответы увидите вы и специалист."
    ),
    instruction=(
        "Ответьте так, как сейчас есть. Можно выбрать «не хочу отвечать» или пропустить "
        "необязательные поля. Нет правильных ответов — это анамнез для совместной работы, "
        "а не клинический тест."
    ),
    duration_minutes=10,
    source_citation="Клинический анамнез / intake для консультации (не стандартизированная шкала).",
    source_urls=(),
    scoring_status="ready",
    items=CLIENT_STATUS_ITEMS,
    scales=(),
    score_fn=score_client_status,
    viz="answers",
    featured=True,
    keep_answers=True,
)
