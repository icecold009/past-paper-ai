from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import CurriculumChapter, Question, QuestionChapterMapping, Subject
from src.db.session import create_db_engine


class CurriculumMapChapter(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    grade_stage: str = Field(min_length=1, max_length=64)
    syllabus_revision: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=0)
    review_status: str = Field(default="pending", min_length=1, max_length=32)
    reviewed_by: str | None = Field(default=None, max_length=320)


class CurriculumMapSubject(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    chapters: list[CurriculumMapChapter] = Field(default_factory=list)


class CurriculumMapMapping(BaseModel):
    subject: str = Field(min_length=1, max_length=16)
    question_id: int = Field(gt=0)
    chapter_code: str = Field(min_length=1, max_length=64)
    grade_stage: str = Field(min_length=1, max_length=64)
    syllabus_revision: str = Field(min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: str = Field(default="pending", min_length=1, max_length=32)
    reviewer_note: str | None = None


class CurriculumMapDocument(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    subjects: list[CurriculumMapSubject] = Field(default_factory=list)
    mappings: list[CurriculumMapMapping] = Field(default_factory=list)


@dataclass(frozen=True)
class CurriculumMapSummary:
    chapters_created_or_updated: int
    mappings_created_or_updated: int
    approved_chapters: int
    approved_mappings: int


def _validate_status(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"pending", "approved", "rejected"}:
        raise ValueError(f"{label} has unsupported review_status: {value!r}")
    return normalized


def _validate_document(document: CurriculumMapDocument) -> CurriculumMapDocument:
    chapter_keys: set[tuple[str, str, str, str]] = set()
    chapter_lookup: set[tuple[str, str, str, str]] = set()
    for subject in document.subjects:
        for chapter in subject.chapters:
            chapter.review_status = _validate_status(chapter.review_status, label=f"chapter {chapter.code}")
            key = (subject.code, chapter.grade_stage, chapter.syllabus_revision, chapter.code)
            if key in chapter_keys:
                raise ValueError(f"Duplicate chapter in curriculum map: {key}")
            chapter_keys.add(key)
            chapter_lookup.add(key)

    for mapping in document.mappings:
        mapping.review_status = _validate_status(
            mapping.review_status,
            label=f"mapping question {mapping.question_id}",
        )
        key = (mapping.subject, mapping.grade_stage, mapping.syllabus_revision, mapping.chapter_code)
        if key not in chapter_lookup:
            raise ValueError(f"Mapping references a chapter missing from the map: {key}")
    return document


def load_curriculum_map(path: Path) -> CurriculumMapDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validator = getattr(CurriculumMapDocument, "model_validate", None)
    document = validator(payload) if validator is not None else CurriculumMapDocument.parse_obj(payload)
    return _validate_document(document)


def upsert_curriculum_map(session: Session, document: CurriculumMapDocument) -> CurriculumMapSummary:
    document = _validate_document(document)
    chapter_by_key: dict[tuple[str, str, str, str], CurriculumChapter] = {}
    chapter_count = 0
    approved_chapters = 0

    for subject_spec in document.subjects:
        subject = session.scalar(select(Subject).where(Subject.code == subject_spec.code))
        if subject is None:
            raise ValueError(f"Subject {subject_spec.code} is not present in the database")
        for chapter_spec in subject_spec.chapters:
            key = (subject_spec.code, chapter_spec.grade_stage, chapter_spec.syllabus_revision, chapter_spec.code)
            chapter = session.scalar(
                select(CurriculumChapter).where(
                    CurriculumChapter.subject_id == subject.id,
                    CurriculumChapter.grade_stage == chapter_spec.grade_stage,
                    CurriculumChapter.syllabus_revision == chapter_spec.syllabus_revision,
                    CurriculumChapter.chapter_code == chapter_spec.code,
                )
            )
            if chapter is None:
                chapter = CurriculumChapter(
                    subject_id=subject.id,
                    grade_stage=chapter_spec.grade_stage,
                    syllabus_revision=chapter_spec.syllabus_revision,
                    chapter_code=chapter_spec.code,
                )
                session.add(chapter)
            chapter.name = chapter_spec.name
            chapter.map_version = document.version
            chapter.position = chapter_spec.position
            chapter.review_status = chapter_spec.review_status
            chapter.reviewed_by = chapter_spec.reviewed_by
            chapter_by_key[key] = chapter
            chapter_count += 1
            approved_chapters += chapter_spec.review_status == "approved"

    session.flush()
    mapping_count = 0
    approved_mappings = 0
    for mapping_spec in document.mappings:
        subject = session.scalar(select(Subject).where(Subject.code == mapping_spec.subject))
        if subject is None:
            raise ValueError(f"Subject {mapping_spec.subject} is not present in the database")
        question = session.get(Question, mapping_spec.question_id)
        if question is None or question.subject_id != subject.id:
            raise ValueError(
                f"Question {mapping_spec.question_id} does not belong to subject {mapping_spec.subject}"
            )
        chapter_key = (
            mapping_spec.subject,
            mapping_spec.grade_stage,
            mapping_spec.syllabus_revision,
            mapping_spec.chapter_code,
        )
        chapter = chapter_by_key[chapter_key]
        link = session.scalar(
            select(QuestionChapterMapping).where(
                QuestionChapterMapping.question_id == question.id,
                QuestionChapterMapping.chapter_id == chapter.id,
            )
        )
        if link is None:
            link = QuestionChapterMapping(question_id=question.id, chapter_id=chapter.id)
            session.add(link)
        link.confidence = mapping_spec.confidence
        link.review_status = mapping_spec.review_status
        link.reviewer_note = mapping_spec.reviewer_note
        mapping_count += 1
        approved_mappings += mapping_spec.review_status == "approved"

    session.commit()
    return CurriculumMapSummary(
        chapters_created_or_updated=chapter_count,
        mappings_created_or_updated=mapping_count,
        approved_chapters=approved_chapters,
        approved_mappings=approved_mappings,
    )


def curriculum_coverage(session: Session, *, subject_code: str) -> dict[str, int | str]:
    subject = session.scalar(select(Subject).where(Subject.code == subject_code.strip()))
    if subject is None:
        raise ValueError(f"Subject {subject_code} is not present in the database")
    total_questions = session.scalar(
        select(func.count()).select_from(Question).where(Question.subject_id == subject.id)
    ) or 0
    approved_chapter_count = session.scalar(
        select(func.count()).select_from(CurriculumChapter).where(
            CurriculumChapter.subject_id == subject.id,
            CurriculumChapter.review_status == "approved",
        )
    ) or 0
    mapped_question_count = session.scalar(
        select(func.count(func.distinct(QuestionChapterMapping.question_id)))
        .select_from(QuestionChapterMapping)
        .join(Question, Question.id == QuestionChapterMapping.question_id)
        .join(CurriculumChapter, CurriculumChapter.id == QuestionChapterMapping.chapter_id)
        .where(
            Question.subject_id == subject.id,
            QuestionChapterMapping.review_status == "approved",
            CurriculumChapter.review_status == "approved",
        )
    ) or 0
    return {
        "subject": subject.code,
        "total_questions": int(total_questions),
        "approved_chapters": int(approved_chapter_count),
        "approved_mapped_questions": int(mapped_question_count),
        "unmapped_questions": max(0, int(total_questions) - int(mapped_question_count)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a reviewed curriculum map into the database")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--database-url")
    args = parser.parse_args()
    document = load_curriculum_map(args.path)
    engine: Engine = create_db_engine(args.database_url)
    try:
        with Session(engine) as session:
            summary = upsert_curriculum_map(session, document)
            print(summary)
            for subject in document.subjects:
                print(curriculum_coverage(session, subject_code=subject.code))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
