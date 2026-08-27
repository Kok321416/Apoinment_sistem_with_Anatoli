"""Specialist type → feature flags (extensible without UI for unused types)."""
from __future__ import annotations

from typing import Iterable

# First phase: only psychologist features are exposed in UI.
FEATURE_DIAGNOSTICS = "diagnostics"

SPECIALTY_FEATURES: dict[str, frozenset[str]] = {
    "psychologist": frozenset({FEATURE_DIAGNOSTICS}),
    # MVP: existing accounts use category «Общая» — keep diagnostics available until specialty is assigned in profile.
    "general": frozenset({FEATURE_DIAGNOSTICS}),
    "coach": frozenset(),
    "tutor": frozenset(),
}

# Map legacy / display category names → specialty codes.
CATEGORY_NAME_TO_CODE: dict[str, str] = {
    "психолог": "psychologist",
    "психология": "psychologist",
    "psychologist": "psychologist",
    "коуч": "coach",
    "coach": "coach",
    "репетитор": "tutor",
    "tutor": "tutor",
    "общая": "general",
    "general": "general",
}


def normalize_specialty_code(raw: str | None) -> str:
    code = (raw or "").strip().lower()
    if code in SPECIALTY_FEATURES:
        return code
    return CATEGORY_NAME_TO_CODE.get(code, "general")


def specialty_code_for_consultant(consultant) -> str:
    """Resolve specialty without triggering async-unsafe lazy loads."""
    cat = None
    try:
        from sqlalchemy import inspect as sa_inspect

        insp = sa_inspect(consultant)
        if insp is not None and "category" not in insp.unloaded:
            cat = consultant.category
    except Exception:
        cat = None
    if cat is None:
        # Relationship not loaded (common on AsyncSession) — safe default.
        return "general"
    code = normalize_specialty_code(getattr(cat, "code", None) or "")
    if code != "general":
        return code
    name = (getattr(cat, "name_category", None) or "").strip().lower()
    return CATEGORY_NAME_TO_CODE.get(name, "general")


def features_for_specialty(code: str) -> frozenset[str]:
    return SPECIALTY_FEATURES.get(normalize_specialty_code(code), frozenset())


def consultant_has_feature(consultant, feature: str) -> bool:
    return feature in features_for_specialty(specialty_code_for_consultant(consultant))


def any_consultant_has_feature(consultants: Iterable, feature: str) -> bool:
    return any(consultant_has_feature(c, feature) for c in consultants)
