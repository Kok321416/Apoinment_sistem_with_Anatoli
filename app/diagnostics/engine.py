"""Diagnostic Engine — scoring and result enrichment (no UI)."""
from __future__ import annotations

from typing import Any

from app.diagnostics.catalog import DISCLAIMER_RU, get_test


def _band_level(band_label: str) -> str:
    """Map methodology band label to UI level: low | medium | elevated | high."""
    t = (band_label or "").lower()
    if any(w in t for w in ("миним", "низк", "слаб")):
        return "low"
    if any(w in t for w in ("лёгк", "легк", "умерен", "средн")):
        return "medium"
    if any(w in t for w in ("повыш", "выше норм")):
        return "elevated"
    if any(w in t for w in ("выраж", "высок", "сильн")):
        return "high"
    return "medium"


def _marker_pct(scale: dict[str, Any]) -> int:
    score = scale.get("score", 0)
    lo = scale.get("min", 0)
    hi = scale.get("max", 0)
    if hi <= lo:
        return 0
    pct = int(round((score - lo) / (hi - lo) * 100))
    return max(0, min(100, pct))


class DiagnosticEngine:
    """Score answers and build a normalized result payload for persistence/display."""

    def score(self, test_code: str, answers: dict[str, Any]) -> dict[str, Any]:
        test = get_test(test_code)
        if not test or not test.runnable or not test.score_fn:
            raise ValueError("Тест недоступен для расчёта")
        raw = test.score_fn(answers, test)
        return self.enrich(raw)

    def enrich(self, result: dict[str, Any]) -> dict[str, Any]:
        interpretation = result.get("interpretation") or {}
        if "disclaimer" not in interpretation:
            interpretation["disclaimer"] = DISCLAIMER_RU
        scales_out = []
        for scale in result.get("scales") or []:
            s = dict(scale)
            label = s.get("band_label") or ""
            s["band_level"] = _band_level(label)
            s["marker_pct"] = _marker_pct(s)
            scales_out.append(s)
        result = dict(result)
        result["scales"] = scales_out
        result["interpretation"] = interpretation
        return result


engine = DiagnosticEngine()
