from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

SUBJECT_PLAN_PATH = Path("config/subject_plan.json")

SUBJECT_PAPER_MARKS: dict[str, dict[str, int]] = {
    "9618": {"p1": 75, "p2": 75, "p3": 75, "p4": 75},
    "9702": {"p1": 40, "p2": 60, "p3": 40, "p4": 100, "p5": 30},
    "9709": {"p1": 75, "p3": 75, "p4": 50, "p5": 50},
    "9231": {"p1": 75, "p2": 75, "p3": 50, "p4": 50},
}


def load_subject_plan(path: Path = SUBJECT_PLAN_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    subjects = payload.get("subjects", [])
    plan: dict[str, list[str]] = {}

    for item in subjects:
        code = str(item.get("code", "")).strip()
        papers = item.get("papers", [])
        if not code:
            continue

        normalized_papers = sorted(
            {str(p).strip().lower() for p in papers if str(p).strip().lower().startswith("p")}
        )
        if normalized_papers:
            plan[code] = normalized_papers
        else:
            plan[code] = []

    return plan


def load_variant_scope(path: Path = SUBJECT_PLAN_PATH) -> set[str]:
    """Load the configured variant scope.

    A one-character token such as ``"2"`` means the two-digit CAIE variant
    code must end in that digit (for example ``12`` or ``22``). A two-digit
    token is treated as an exact variant code.
    """

    if not path.exists():
        return set()

    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("variants", [])
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def variant_in_scope(variant: object, allowed_variants: Iterable[str] | None) -> bool:
    """Return whether a normalized filename variant is in the configured scope."""

    if allowed_variants is None:
        return True

    normalized_variant = str(variant).strip()
    scopes = {str(value).strip() for value in allowed_variants if str(value).strip()}
    if not scopes:
        return True

    return any(
        normalized_variant == scope
        if len(scope) == 2
        else normalized_variant.endswith(scope)
        for scope in scopes
    )
