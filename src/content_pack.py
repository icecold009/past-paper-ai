from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import MarkSchemePoint, Question, Subject
from src.db.session import create_db_engine


class ContentPackPoint(BaseModel):
    point_text: str = Field(min_length=1)
    marks_value: int = Field(default=1, ge=1)


class ContentPackQuestion(BaseModel):
    subject: str = Field(min_length=1, max_length=16)
    subject_name: str = Field(min_length=1, max_length=255)
    paper: str = Field(default="starter", min_length=1, max_length=16)
    year: int = Field(default=2026, ge=2000)
    session: str = Field(default="Starter pack", min_length=1, max_length=32)
    variant: str = Field(default="1", min_length=1, max_length=8)
    question_number: str = Field(min_length=1, max_length=16)
    sub_label: str = ""
    topic: str = Field(min_length=1, max_length=255)
    subtopic: str = ""
    command_word: str = Field(min_length=1, max_length=64)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    marks: int = Field(ge=1)
    question_text: str = Field(min_length=1)
    mark_scheme_points: list[ContentPackPoint] = Field(min_length=1)


class ContentPack(BaseModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    questions: list[ContentPackQuestion] = Field(min_length=1)


def load_content_pack(path: Path) -> ContentPack:
    return ContentPack.model_validate_json(path.read_text(encoding="utf-8"))


def ingest_content_pack(path: Path, *, engine: Engine | None = None) -> dict[str, int]:
    pack = load_content_pack(path)
    owns_engine = engine is None
    engine = engine or create_db_engine()
    question_count = 0
    point_count = 0
    try:
        with Session(engine) as session:
            with session.begin():
                subject_cache: dict[str, Subject] = {}
                for item in pack.questions:
                    subject = subject_cache.get(item.subject)
                    if subject is None:
                        subject = session.scalar(select(Subject).where(Subject.code == item.subject))
                        if subject is None:
                            subject = Subject(code=item.subject, name=item.subject_name)
                            session.add(subject)
                            session.flush()
                        else:
                            subject.name = item.subject_name
                        subject_cache[item.subject] = subject

                    question = session.scalar(
                        select(Question).where(
                            Question.subject_id == subject.id,
                            Question.paper == item.paper,
                            Question.year == item.year,
                            Question.session == item.session,
                            Question.variant == item.variant,
                            Question.question_number == item.question_number,
                            Question.sub_label == item.sub_label,
                        )
                    )
                    if question is None:
                        question = Question(
                            subject_id=subject.id,
                            paper=item.paper,
                            year=item.year,
                            session=item.session,
                            variant=item.variant,
                            question_number=item.question_number,
                            sub_label=item.sub_label,
                            topic=item.topic,
                            subtopic=item.subtopic,
                            command_word=item.command_word,
                            difficulty=item.difficulty,
                            marks=item.marks,
                            raw_text=item.question_text,
                        )
                        session.add(question)
                        session.flush()
                    question.topic = item.topic
                    question.subtopic = item.subtopic
                    question.command_word = item.command_word
                    question.difficulty = item.difficulty
                    question.marks = item.marks
                    question.raw_text = item.question_text
                    session.execute(delete(MarkSchemePoint).where(MarkSchemePoint.question_id == question.id))
                    for point in item.mark_scheme_points:
                        session.add(
                            MarkSchemePoint(
                                question_id=question.id,
                                point_text=point.point_text,
                                marks_value=point.marks_value,
                            )
                        )
                        point_count += 1
                    question_count += 1
        return {"questions": question_count, "mark_scheme_points": point_count}
    finally:
        if owns_engine:
            engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load a normalized Section B content pack")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--database-url")
    args = parser.parse_args()
    engine = create_db_engine(args.database_url)
    try:
        print(ingest_content_pack(args.path, engine=engine))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
