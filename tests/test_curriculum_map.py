from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.curriculum_map import (
    CurriculumMapDocument,
    curriculum_coverage,
    upsert_curriculum_map,
)
from src.db.models import Base, CurriculumChapter, Question, QuestionChapterMapping, Subject


class CurriculumMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            subject = Subject(code="9618", name="Computer Science")
            session.add(subject)
            session.flush()
            session.add(
                Question(
                    id=1,
                    subject_id=subject.id,
                    paper="p1",
                    year=2023,
                    session="May/June",
                    variant="12",
                    question_number="1",
                    sub_label="",
                    raw_text="State one fact.",
                )
            )
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def _document(self) -> CurriculumMapDocument:
        return CurriculumMapDocument(
            version="school-map-2025-v1",
            subjects=[
                {
                    "code": "9618",
                    "chapters": [
                        {
                            "code": "1.1",
                            "name": "Information representation",
                            "grade_stage": "AS",
                            "syllabus_revision": "2025",
                            "position": 1,
                            "review_status": "approved",
                            "reviewed_by": "teacher@example.test",
                        }
                    ],
                }
            ],
            mappings=[
                {
                    "subject": "9618",
                    "question_id": 1,
                    "chapter_code": "1.1",
                    "grade_stage": "AS",
                    "syllabus_revision": "2025",
                    "confidence": 1.0,
                    "review_status": "approved",
                }
            ],
        )

    def test_import_is_idempotent_and_reports_approved_coverage(self) -> None:
        with Session(self.engine) as session:
            first = upsert_curriculum_map(session, self._document())
            second = upsert_curriculum_map(session, self._document())
            self.assertEqual(first, second)
            self.assertEqual(first.approved_chapters, 1)
            self.assertEqual(first.approved_mappings, 1)
            self.assertEqual(curriculum_coverage(session, subject_code="9618")["unmapped_questions"], 0)
            self.assertEqual(session.scalar(select(CurriculumChapter.map_version)), "school-map-2025-v1")
            self.assertEqual(session.scalar(select(QuestionChapterMapping.review_status)), "approved")

    def test_mapping_must_reference_a_declared_chapter(self) -> None:
        document = self._document()
        document.mappings[0].chapter_code = "missing"
        with self.assertRaises(ValueError):
            upsert_curriculum_map(Session(self.engine), document)


if __name__ == "__main__":
    unittest.main()
