from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db.ingest import ingest_subject
from src.db.models import (
    Base,
    CurriculumChapter,
    DiagnosticEvidence,
    MarkSchemePoint,
    Question,
    QuestionChapterMapping,
    Recommendation,
    Subject,
    User,
)


class DatabaseIngestTests(unittest.TestCase):
    def test_ingest_is_idempotent_and_loads_subquestions_and_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tagged_csv = temp_path / "tagged.csv"
            pairs_csv = temp_path / "pairs.csv"
            pd.DataFrame(
                [
                    {
                        "question_id": "q1",
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                        "question_number": "1",
                        "question_text": "Question text",
                        "subquestions": json.dumps(
                            [{"label": "(a)", "text": "State one thing.", "marks": 2}]
                        ),
                        "total_marks": 2,
                        "subquestion_tags": json.dumps(
                            [
                                {
                                    "label": "(a)",
                                    "text": "State one thing.",
                                    "marks": 2,
                                    "topic": "Memory",
                                    "subtopic": "Cache",
                                    "command_word": "State",
                                    "difficulty": "easy",
                                }
                            ]
                        ),
                        "mark_scheme_points": json.dumps(["Reduces access time"]),
                    }
                ]
            ).to_csv(tagged_csv, index=False)
            pd.DataFrame(
                [
                    {
                        "subject": "9618",
                        "paper": "p1",
                        "year": 2023,
                        "session": "May/June",
                        "variant": "11",
                    }
                ]
            ).to_csv(pairs_csv, index=False)

            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            first = ingest_subject(
                "9618",
                engine=engine,
                tagged_csv=tagged_csv,
                pairs_csv=pairs_csv,
            )
            second = ingest_subject(
                "9618",
                engine=engine,
                tagged_csv=tagged_csv,
                pairs_csv=pairs_csv,
            )

            with Session(engine) as session:
                subject_count = session.scalar(select(func.count()).select_from(Subject))
                question_count = session.scalar(select(func.count()).select_from(Question))
                point_count = session.scalar(select(func.count()).select_from(MarkSchemePoint))

        self.assertEqual(first, {"subjects": 1, "questions": 2, "mark_scheme_points": 1})
        self.assertEqual(second, first)
        self.assertEqual((subject_count, question_count, point_count), (1, 2, 1))

    def test_personalization_entities_preserve_review_and_evidence_boundaries(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            subject = Subject(code="9618", name="Computer Science")
            user = User(email="student@example.test")
            session.add_all([subject, user])
            session.flush()
            chapter = CurriculumChapter(
                subject_id=subject.id,
                grade_stage="AS",
                syllabus_revision="2025",
                chapter_code="1.1",
                name="Information representation",
                review_status="approved",
                reviewed_by="teacher@example.test",
            )
            question = Question(
                subject_id=subject.id,
                paper="p1",
                year=2023,
                session="May/June",
                variant="12",
                question_number="1",
                sub_label="",
                raw_text="Describe a representation.",
            )
            session.add_all([chapter, question])
            session.flush()
            session.add(QuestionChapterMapping(
                question_id=question.id,
                chapter_id=chapter.id,
                confidence=1.0,
                review_status="approved",
            ))
            session.add(DiagnosticEvidence(
                user_id=user.id,
                chapter_id=chapter.id,
                source_type="marked_attempt",
                evidence_count=2,
                score=0.5,
                confidence=0.78,
                state="needs_practice",
            ))
            session.add(Recommendation(
                user_id=user.id,
                chapter_id=chapter.id,
                state="needs_practice",
                reason="Two recent marked attempts were below the target range.",
                evidence_count=2,
                confidence=0.78,
                activity_type="targeted_practice",
                rule_version="rules-v1",
            ))
            session.commit()

            assert session.scalar(select(func.count()).select_from(CurriculumChapter)) == 1
            assert session.scalar(select(func.count()).select_from(QuestionChapterMapping)) == 1
            assert session.scalar(select(func.count()).select_from(DiagnosticEvidence)) == 1
            assert session.scalar(select(func.count()).select_from(Recommendation)) == 1


if __name__ == "__main__":
    unittest.main()
