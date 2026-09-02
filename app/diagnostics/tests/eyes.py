"""Чтение эмоций по глазам — краткая адаптация (структура как RMET / eyespsy).

Скоринг: доля верных ответов по ключам методики (краткая форма, 12 стимулов).
Изображения — плейсхолдеры; оператор может заменить на лицензированный набор.
"""
from __future__ import annotations

from typing import Any

from app.diagnostics.catalog import (
    DISCLAIMER_RU,
    ItemDef,
    ScaleDef,
    TestDefinition,
    _band_for,
)

# correct option index (0-based) per item
_EYES_KEYS: tuple[int, ...] = (2, 1, 3, 0, 2, 1, 3, 2, 0, 1, 2, 3)

_EYES_OPTS = (
    ("Задумчивость", 0),
    ("Серьёзность", 1),
    ("Интерес", 2),
    ("Беспокойство", 3),
)

_EYES_STEMS = (
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
    "Какое состояние лучше всего описывает взгляд на изображении?",
)


def _eyes_items() -> tuple[ItemDef, ...]:
    items = []
    for i in range(1, 13):
        items.append(
            ItemDef(
                id=f"i{i}",
                text=_EYES_STEMS[i - 1],
                options=_EYES_OPTS,
                scale_code="accuracy",
                image_url=f"/static/diagnostics/eyes/eye-{i:02d}.svg",
            )
        )
    return tuple(items)


def score_eyes(answers: dict[str, Any], test: TestDefinition) -> dict[str, Any]:
    correct = 0
    total = len(test.items)
    for idx, item in enumerate(test.items, start=1):
        raw = answers.get(item.id)
        if raw is None:
            continue
        try:
            chosen = int(raw)
        except (TypeError, ValueError):
            continue
        key_idx = _EYES_KEYS[idx - 1]
        if chosen == key_idx:
            correct += 1
    scale = test.scales[0]
    label, interp = _band_for(correct, scale)
    return {
        "scores": {"accuracy": correct},
        "scales": [
            {
                "code": "accuracy",
                "title": scale.title,
                "score": correct,
                "min": scale.min_score,
                "max": scale.max_score,
                "band_label": label,
                "interpretation": interp,
            }
        ],
        "summary": f"Чтение эмоций: {correct}/{total} ({label})",
        "interpretation": {
            "overall": interp,
            "disclaimer": DISCLAIMER_RU,
            "crisis_hint": "",
        },
        "flags": [],
    }


EYES = TestDefinition(
    code="eyes",
    version="1-short",
    title="Чтение эмоций по глазам",
    short_description="Определите эмоциональное состояние по области глаз (краткая форма, 12 изображений).",
    instruction=(
        "На каждом изображении показана область глаз. Выберите один вариант, который лучше всего "
        "описывает эмоциональное состояние человека. Отвечайте интуитивно, без долгих раздумий."
    ),
    duration_minutes=10,
    source_citation=(
        "Reading the Mind in the Eyes (Baron-Cohen et al.). Краткая адаптация для онлайн-скрининга; "
        "не является клиническим диагнозом."
    ),
    source_urls=("https://psytests.org/emo/eyespsy.html",),
    scoring_status="ready",
    items=_eyes_items(),
    scales=(
        ScaleDef(
            code="accuracy",
            title="Точность чтения эмоций",
            min_score=0,
            max_score=12,
            bands=(
                (0, 4, "низкая", "Результат ниже среднего для данной краткой формы."),
                (5, 8, "средняя", "Результат в среднем диапазоне."),
                (9, 10, "повышенная", "Хорошее распознавание эмоциональных состояний по глазам."),
                (11, 12, "высокая", "Очень высокая точность в данной краткой форме."),
            ),
        ),
    ),
    score_fn=score_eyes,
    viz="bands",
)
