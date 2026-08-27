from __future__ import annotations

import unittest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from api.auth import issue_token, verify_token
from api.main import (
    create_app,
    create_practice_session,
    get_guidance,
    save_practice_answer,
    start_diagnostic,
    submit_practice_session,
)
from api.personalization import build_guidance
from api.schemas import DiagnosticStartRequest, DiagnosticResponseSave, PracticeSessionCreate
from src.db.models import (
    Attempt,
    Base,
    CurriculumChapter,
    MarkSchemePoint,
    Question,
    QuestionChapterMapping,
    Subject,
    User,
)


class PersonalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            subject = Subject(code="9618", name="Computer Science")
            user = User(id=7, email="personalization@example.test", school_id="school-a", grade_stage="AS")
            session.add_all([subject, user])
            session.flush()
            chapter = CurriculumChapter(
                subject_id=subject.id,
                grade_stage="AS",
                syllabus_revision="2025",
                chapter_code="1.1",
                name="Information representation",
                position=1,
                review_status="approved",
            )
            pending = CurriculumChapter(
                subject_id=subject.id,
                grade_stage="AS",
                syllabus_revision="2025",
                chapter_code="1.2",
                name="Pending chapter",
                position=2,
                review_status="pending",
            )
            session.add_all([chapter, pending])
            session.flush()
            question = Question(
                id=101,
                subject_id=subject.id,
                paper="p1",
                year=2023,
                session="May/June",
                variant="12",
                question_number="1",
                sub_label="",
                topic="Information representation",
                subtopic="Data",
                command_word="Explain",
                marks=2,
                raw_text="Explain one representation.",
            )
            pending_question = Question(
                id=102,
                subject_id=subject.id,
                paper="p1",
                year=2023,
                session="May/June",
                variant="12",
                question_number="2",
                sub_label="",
                topic="Pending",
                subtopic="Pending",
                command_word="State",
                marks=1,
                raw_text="State one pending fact.",
            )
            session.add_all([question, pending_question])
            session.flush()
            session.add_all(
                [
                    QuestionChapterMapping(
                        question_id=question.id,
                        chapter_id=chapter.id,
                        confidence=1.0,
                        review_status="approved",
                    ),
                    QuestionChapterMapping(
                        question_id=pending_question.id,
                        chapter_id=pending.id,
                        confidence=1.0,
                        review_status="pending",
                    ),
                    MarkSchemePoint(question_id=question.id, point_text="A valid explanation", marks_value=2),
                ]
            )
            session.commit()

        self.auth = verify_token(
            issue_token(user_id=7, secret="test-secret", school_id="school-a"),
            "test-secret",
        )
        self.app = create_app(
            engine=self.engine,
            auth_secret="test-secret",
        )
        self.request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "headers": [],
                "query_string": b"",
                "app": self.app,
            }
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_guidance_starts_with_insufficient_evidence_and_ignores_pending_content(self) -> None:
        with Session(self.engine) as session:
            guidance = build_guidance(session, user_id=7, subject_id=1)
            self.assertEqual(guidance.state, "start_diagnostic")
            self.assertEqual(len(guidance.chapters), 1)
            self.assertIsNone(guidance.recommendation)

    def test_guidance_creates_explainable_recommendation_after_two_attempts(self) -> None:
        with Session(self.engine) as session:
            session.add_all(
                [
                    Attempt(
                        user_id=7,
                        question_id=101,
                        submitted_answer_text="weak",
                        points_awarded={},
                        marks_earned=0,
                        marks_possible=2,
                    ),
                    Attempt(
                        user_id=7,
                        question_id=101,
                        submitted_answer_text="still weak",
                        points_awarded={},
                        marks_earned=1,
                        marks_possible=2,
                    ),
                ]
            )
            session.commit()
            guidance = build_guidance(session, user_id=7, subject_id=1)
            self.assertEqual(guidance.state, "needs_practice")
            assert guidance.recommendation is not None
            self.assertIn("targeted practice", guidance.recommendation.reason)
            self.assertEqual(guidance.recommendation.rule_version, "deterministic-v1")

    def test_auth_token_rejects_tampering_and_expiry(self) -> None:
        token = issue_token(user_id=7, secret="test-secret", expires_at=100)
        with self.assertRaises(HTTPException):
            verify_token(token + "x", "test-secret", now=1)
        with self.assertRaises(HTTPException):
            verify_token(token, "test-secret", now=100)

    def test_secure_guidance_rejects_cross_user_access(self) -> None:
        with Session(self.engine) as session:
            with self.assertRaises(HTTPException) as raised:
                get_guidance(user_id=8, subject="9618", auth=self.auth, session=session)
        self.assertEqual(raised.exception.status_code, 403)

    def test_diagnostic_and_practice_sessions_are_idempotent_and_stateful(self) -> None:
        with Session(self.engine) as session:
            first = start_diagnostic(
                DiagnosticStartRequest(
                    user_id=7,
                    subject="9618",
                    grade_stage="AS",
                    idempotency_key="diagnostic-1",
                ),
                auth=self.auth,
                session=session,
            )
            second = start_diagnostic(
                DiagnosticStartRequest(
                    user_id=7,
                    subject="9618",
                    grade_stage="AS",
                    idempotency_key="diagnostic-1",
                ),
                auth=self.auth,
                session=session,
            )
            self.assertEqual(first.id, second.id)

            practice = create_practice_session(
                PracticeSessionCreate(
                    user_id=7,
                    subject="9618",
                    question_ids=[101],
                    idempotency_key="practice-1",
                ),
                auth=self.auth,
                session=session,
            )
            repeated = create_practice_session(
                PracticeSessionCreate(
                    user_id=7,
                    subject="9618",
                    question_ids=[101],
                    idempotency_key="practice-1",
                ),
                auth=self.auth,
                session=session,
            )
            self.assertEqual(practice.id, repeated.id)
            saved = save_practice_answer(
                practice.id,
                101,
                DiagnosticResponseSave(user_id=7, answer_text="A valid answer"),
                auth=self.auth,
                session=session,
            )
            self.assertEqual(saved.answer_text, "A valid answer")
            submitted = submit_practice_session(practice.id, user_id=7, auth=self.auth, session=session)
            self.assertEqual(submitted.state, "submitted")

        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(User).where(User.id == 7)).school_id, "school-a")


if __name__ == "__main__":
    unittest.main()
