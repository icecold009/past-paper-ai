from __future__ import annotations

import json
from pathlib import Path

SUBJECT_PLAN_PATH = Path(__file__).resolve().parents[1] / "config/subject_plan.json"

SUBJECT_PAPER_MARKS: dict[str, dict[str, int]] = {
    "9618": {"p1": 75, "p2": 75},
    "9702": {"p1": 40, "p2": 60},
    "9709": {"p1": 75, "p5": 50},
    "9231": {"p1": 75, "p4": 50},
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
