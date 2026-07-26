from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import MarkSchemePoint, Question, Subject
from src.db.session import create_db_engine
from src.paths import qp_ms_pairs_csv_path, tagged_questions_csv_path
from src.subject_plan import load_subject_plan

logger = logging.getLogger(__name__)

_TAGGED_REQUIRED_COLUMNS = {
    "subject",
    "paper",
    "year",
    "session",
    "variant",
    "question_number",
    "question_text",
    "subquestions",
}
_PAIR_REQUIRED_COLUMNS = {"subject", "paper", "year", "session", "variant"}


def _subject_name(subject: str, plan_path: Path = Path("config/subject_plan.json")) -> str:
    if plan_path.exists():
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        for item in payload.get("subjects", []):
            if str(item.get("code", "")).strip() == str(subject):
                return str(item.get("name", subject)).strip() or str(subject)
    return str(subject)


def _json_list(value: object) -> list[Any]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _text(value: object) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _optional_int(value: object) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _match_key(row: pd.Series) -> tuple[str, str, int, str, str]:
    return (
        str(row["subject"]),
        str(row["paper"]),
        int(row["year"]),
        str(row["session"]),
        str(row["variant"]),
    )


def _load_tagged_questions(path: Path, subject: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing tagged questions CSV: {path}. Run the tag step first.")
    tagged = pd.read_csv(path)
    missing = _TAGGED_REQUIRED_COLUMNS.difference(set(tagged.columns))
    if missing:
        raise ValueError(f"Tagged CSV missing required columns: {', '.join(sorted(missing))}")
    return tagged[tagged["subject"].astype(str).str.strip() == str(subject)].copy()


def _load_pair_keys(path: Path, subject: str) -> set[tuple[str, str, int, str, str]]:
    if not path.exists():
        logger.warning("Missing QP/MS pairs CSV: %s; no mark-scheme points will be attached", path)
        return set()
    pairs = pd.read_csv(path)
    missing = _PAIR_REQUIRED_COLUMNS.difference(set(pairs.columns))
    if missing:
        raise ValueError(f"Pairs CSV missing required columns: {', '.join(sorted(missing))}")
    filtered = pairs[pairs["subject"].astype(str).str.strip() == str(subject)]
    return {_match_key(row) for _, row in filtered.iterrows()}


def _question_units(row: pd.Series) -> list[dict[str, Any]]:
    raw_units = _json_list(row.get("subquestions", "[]"))
    tagged_units = _json_list(row.get("subquestion_tags", "[]"))
    raw_by_label = {str(unit.get("label", "")): unit for unit in raw_units if isinstance(unit, dict)}

    if not tagged_units:
        return raw_units

    merged: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for tagged_unit in tagged_units:
        if not isinstance(tagged_unit, dict):
            continue
        label = str(tagged_unit.get("label", ""))
        base = raw_by_label.get(label, {})
        merged.append({**base, **tagged_unit})
        seen_labels.add(label)

    # Preserve a subquestion when a malformed Gemini response caused its tag to be skipped.
    merged.extend(unit for label, unit in raw_by_label.items() if label not in seen_labels)
    return merged


def _upsert_subject(session: Session, code: str, name: str) -> Subject:
    subject = session.scalar(select(Subject).where(Subject.code == code))
    if subject is None:
        subject = Subject(code=code, name=name)
        session.add(subject)
        session.flush()
    elif subject.name != name:
        subject.name = name
    return subject


def _upsert_question(
    session: Session,
    *,
    subject_id: int,
    paper: str,
    year: int,
    session_name: str,
    variant: str,
    question_number: str,
    sub_label: str,
    topic: str | None,
    subtopic: str | None,
    command_word: str | None,
    difficulty: str | None,
    marks: int | None,
    raw_text: str,
) -> Question:
    filters = (
        Question.subject_id == subject_id,
        Question.paper == paper,
        Question.year == year,
        Question.session == session_name,
        Question.variant == variant,
        Question.question_number == question_number,
        Question.sub_label == sub_label,
    )
    question = session.scalar(select(Question).where(*filters))
    values = {
        "subject_id": subject_id,
        "paper": paper,
        "year": year,
        "session": session_name,
        "variant": variant,
        "question_number": question_number,
        "sub_label": sub_label,
        "topic": topic,
        "subtopic": subtopic,
        "command_word": command_word,
        "difficulty": difficulty,
        "marks": marks,
        "raw_text": raw_text,
    }
    if question is None:
        question = Question(**values)
        session.add(question)
        session.flush()
    else:
        for key, value in values.items():
            setattr(question, key, value)
    return question


def _points(value: object) -> list[tuple[str, int | None]]:
    parsed = _json_list(value)
    result: list[tuple[str, int | None]] = []
    for point in parsed:
        if isinstance(point, dict):
            text = _text(point.get("point_text", point.get("text", point.get("point", ""))))
            marks = _optional_int(point.get("marks_value", point.get("marks")))
        else:
            text = _text(point)
            marks = None
        if text:
            result.append((text, marks))
    return result


def _replace_mark_scheme_points(
    session: Session,
    question: Question,
    points: list[tuple[str, int | None]],
) -> int:
    session.execute(delete(MarkSchemePoint).where(MarkSchemePoint.question_id == question.id))
    for point_text, marks_value in points:
        session.add(
            MarkSchemePoint(
                question_id=question.id,
                point_text=point_text,
                marks_value=marks_value,
            )
        )
    return len(points)


def ingest_subject(
    subject: str,
    *,
    engine: Engine | None = None,
    tagged_csv: Path | None = None,
    pairs_csv: Path | None = None,
) -> dict[str, int]:
    """Idempotently ingest one subject's tagged questions and paired MS points."""

    tagged_csv = tagged_csv or tagged_questions_csv_path(subject)
    pairs_csv = pairs_csv or qp_ms_pairs_csv_path(subject)
    tagged = _load_tagged_questions(tagged_csv, subject)
    pair_keys = _load_pair_keys(pairs_csv, subject)
    owns_engine = engine is None
    engine = engine or create_db_engine()

    question_count = 0
    point_count = 0
    with Session(engine) as session:
        with session.begin():
            db_subject = _upsert_subject(session, str(subject), _subject_name(subject))
            for _, row in tagged.iterrows():
                key = _match_key(row)
                question_number = str(row["question_number"])
                parent = _upsert_question(
                    session,
                    subject_id=db_subject.id,
                    paper=str(row["paper"]),
                    year=int(row["year"]),
                    session_name=str(row["session"]),
                    variant=str(row["variant"]),
                    question_number=question_number,
                    sub_label="",
                    topic=_optional_text(row.get("topic")),
                    subtopic=_optional_text(row.get("subtopic")),
                    command_word=_optional_text(row.get("command_word")),
                    difficulty=_optional_text(row.get("difficulty")),
                    marks=_optional_int(row.get("total_marks", row.get("marks"))),
                    raw_text=_text(row["question_text"]),
                )
                question_count += 1

                for unit in _question_units(row):
                    label = _text(unit.get("label"))
                    if not label:
                        continue
                    _upsert_question(
                        session,
                        subject_id=db_subject.id,
                        paper=str(row["paper"]),
                        year=int(row["year"]),
                        session_name=str(row["session"]),
                        variant=str(row["variant"]),
                        question_number=question_number,
                        sub_label=label,
                        topic=_optional_text(unit.get("topic")),
                        subtopic=_optional_text(unit.get("subtopic")),
                        command_word=_optional_text(unit.get("command_word")),
                        difficulty=_optional_text(unit.get("difficulty")),
                        marks=_optional_int(unit.get("marks")),
                        raw_text=_text(unit.get("text")),
                    )
                    question_count += 1

                points = _points(row.get("mark_scheme_points", "[]")) if key in pair_keys else []
                if key not in pair_keys and _points(row.get("mark_scheme_points", "[]")):
                    logger.warning(
                        "Ignoring mark-scheme points for %s because no matched pair exists",
                        key,
                    )
                point_count += _replace_mark_scheme_points(session, parent, points)

    if owns_engine:
        engine.dispose()
    return {"subjects": 1, "questions": question_count, "mark_scheme_points": point_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest tagged questions into the database")
    parser.add_argument("--subject", action="append", help="Subject code; repeat for multiple subjects")
    parser.add_argument("--database-url", help="Override DATABASE_URL from .env")
    args = parser.parse_args()
    subjects = args.subject or sorted(load_subject_plan())
    if not subjects:
        parser.error("pass --subject or configure subjects in config/subject_plan.json")

    engine = create_db_engine(args.database_url)
    try:
        for subject in subjects:
            summary = ingest_subject(subject, engine=engine)
            print(f"Ingested {subject}: {summary}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
