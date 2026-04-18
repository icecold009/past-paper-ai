from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.paths import BLUEPRINT_JSON, QUESTION_STATS_CSV, QUESTIONS_CSV, REPRESENTATIVE_QUESTIONS_CSV


def _build_blueprint_scaffold(questions: pd.DataFrame) -> dict[str, object]:
    available_papers = sorted({str(p).lower() for p in questions["paper"].dropna().unique().tolist()})
    return {
        "subject": "9618",
        "papers_available": available_papers,
        "scaffold": {
            "p1": {
                "target_total_marks": 75,
                "target_question_count": 8,
                "notes": "Hardcoded scaffold for now; refine from measured stats later.",
            },
            "p2": {
                "target_total_marks": 75,
                "target_question_count": 10,
                "notes": "Hardcoded scaffold for now; refine from measured stats later.",
            },
        },
    }


def _representative_samples(questions: pd.DataFrame) -> pd.DataFrame:
    if questions.empty:
        return questions.head(0).copy()

    sampled_frames: list[pd.DataFrame] = []
    for paper, paper_df in questions.groupby("paper"):
        working = paper_df.sort_values("question_text_length")
        n = len(working)
        if n == 1:
            sampled_frames.append(working.head(1))
            continue

        indexes = sorted({0, n // 2, n - 1})
        sampled_frames.append(working.iloc[indexes])

    combined = pd.concat(sampled_frames, ignore_index=True)
    return combined.drop_duplicates(subset=["question_id"])


def analyze_questions(
    questions_csv: Path = QUESTIONS_CSV,
    stats_csv: Path = QUESTION_STATS_CSV,
    representative_csv: Path = REPRESENTATIVE_QUESTIONS_CSV,
    blueprint_json: Path = BLUEPRINT_JSON,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if not questions_csv.exists():
        raise FileNotFoundError(f"Missing questions CSV: {questions_csv}. Run segmentation first.")

    questions = pd.read_csv(questions_csv)
    required_columns = {"question_id", "paper", "year", "question_text", "question_text_length"}
    missing = required_columns.difference(set(questions.columns))
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise ValueError(f"Questions CSV missing required columns: {missing_csv}")

    stats = (
        questions.groupby(["paper", "year"], dropna=False)
        .agg(
            question_count=("question_id", "count"),
            avg_text_length=("question_text_length", "mean"),
            median_text_length=("question_text_length", "median"),
        )
        .reset_index()
        .sort_values(["paper", "year"])
    )

    representative = _representative_samples(questions)
    blueprint = _build_blueprint_scaffold(questions)

    stats_csv.parent.mkdir(parents=True, exist_ok=True)
    representative_csv.parent.mkdir(parents=True, exist_ok=True)
    blueprint_json.parent.mkdir(parents=True, exist_ok=True)

    stats.to_csv(stats_csv, index=False, encoding="utf-8")
    representative.to_csv(representative_csv, index=False, encoding="utf-8")
    blueprint_json.write_text(json.dumps(blueprint, indent=2), encoding="utf-8")

    print(f"Wrote question stats to {stats_csv}")
    print(f"Wrote representative samples to {representative_csv}")
    print(f"Wrote blueprint scaffold to {blueprint_json}")
    return stats, representative, blueprint


if __name__ == "__main__":
    analyze_questions()
