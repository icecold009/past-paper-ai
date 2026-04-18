from __future__ import annotations

import json
from pathlib import Path

SUBJECT_PLAN_PATH = Path("config/subject_plan.json")


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
