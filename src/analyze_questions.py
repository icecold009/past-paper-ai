from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.paths import (
    blueprint_json_path,
    question_stats_csv_path,
    questions_csv_path,
    representative_questions_csv_path,
)
from src.subject_plan import SUBJECT_PAPER_MARKS


def _build_blueprint_scaffold(
    subject: str,
    questions: pd.DataFrame,
    planned_papers: list[str] | None = None,
) -> dict[str, object]:
    available_papers = sorted({str(p).lower() for p in questions["paper"].dropna().unique().tolist()})
    scaffold_papers = sorted({p.lower() for p in (planned_papers or available_papers)})

    paper_scaffold: dict[str, dict[str, object]] = {}
    for paper in scaffold_papers:
        paper_rows = questions[questions["paper"].astype(str).str.lower() == paper]
        if paper_rows.empty:
            target_question_count = 8
        else:
            year_counts = paper_rows.groupby("year")["question_id"].count()
            target_question_count = int(year_counts.median()) if not year_counts.empty else 8

        subject_marks = SUBJECT_PAPER_MARKS.get(subject, {})
        marks = subject_marks.get(paper)
        if marks is None:
            print(
                f"Warning: no configured mark total for {subject}/{paper.upper()}, defaulting to 75. "
                "Add it to SUBJECT_PAPER_MARKS in src/subject_plan.py to suppress this warning."
            )
            marks = 75

        paper_scaffold[paper] = {
            "target_total_marks": marks,
            "target_question_count": max(target_question_count, 1),
            "notes": "Hardcoded scaffold for now; refine from measured stats later.",
        }

    return {
        "subject": subject,
        "papers_available": available_papers,
        "scaffold": paper_scaffold,
    }


def _representative_samples(questions: pd.DataFrame) -> pd.DataFrame:
    if questions.empty:
        return questions.head(0).copy()

    sampled_frames: list[pd.DataFrame] = []
    for paper, paper_df in questions.groupby("paper"):
        working = paper_df.sort_values("question_text_length")
        n = len(working)
        if n <= 5:
            sampled_frames.append(working)
            continue

        target_count = min(8, max(5, round(n ** 0.5)))
        indexes = sorted(
            {
                round(i * (n - 1) / (target_count - 1))
                for i in range(target_count)
            }
        )
        sampled_frames.append(working.iloc[indexes])

    combined = pd.concat(sampled_frames, ignore_index=True)
    return combined.drop_duplicates(subset=["question_id"])


def analyze_questions(
    subject: str,
    planned_papers: list[str] | None = None,
    questions_csv: Path | None = None,
    stats_csv: Path | None = None,
    representative_csv: Path | None = None,
    blueprint_json: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    if questions_csv is None:
        questions_csv = questions_csv_path(subject)
    if stats_csv is None:
        stats_csv = question_stats_csv_path(subject)
    if representative_csv is None:
        representative_csv = representative_questions_csv_path(subject)
    if blueprint_json is None:
        blueprint_json = blueprint_json_path(subject)

    if not questions_csv.exists():
        raise FileNotFoundError(f"Missing questions CSV: {questions_csv}. Run segmentation first.")

    questions = pd.read_csv(questions_csv)
    required_columns = {"question_id", "paper", "year", "question_text", "question_text_length"}
    missing = required_columns.difference(set(questions.columns))
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise ValueError(f"Questions CSV missing required columns: {missing_csv}")

    if "doc_type" in questions.columns:
        questions = questions[questions["doc_type"].astype(str).str.lower() == "qp"].copy()

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
    blueprint = _build_blueprint_scaffold(subject, questions, planned_papers=planned_papers)

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
    print("Use `python -m src.cli analyze --subject <code>` to run analysis.")
