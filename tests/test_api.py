from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from starlette.requests import Request

from api.grading import GeminiGrade, grade_answer
from api.main import create_app, create_attempt, get_mastery, list_questions, list_subjects
from api.schemas import AttemptCreate
from src.db.models import Attempt, Base, MarkSchemePoint, Mastery, Question, Subject, User


class _FakeGrader:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> GeminiGrade:
        self.calls.append(kwargs)
        return GeminiGrade(
            points_hit=["Uses a cache"],
            points_missed=["Explains the performance benefit"],
            marks_earned=1,
            feedback="Good identification; add the effect on access time.",
        )


class _FakeGeminiModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def generate_content(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(text=next(self.responses))


class ApiTests(unittest.TestCase):
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
            session.add(User(id=7, email="student@example.test"))
            question = Question(
                id=11,
                subject_id=subject.id,
                paper="p1",
                year=2023,
                session="May/June",
                variant="11",
                question_number="1",
                sub_label="",
                topic="Data representation",
                subtopic="Cache",
                command_word="Explain",
                difficulty="easy",
                marks=2,
                raw_text="Explain one benefit of cache memory.",
            )
            session.add(question)
            session.flush()
            session.add(
                MarkSchemePoint(
                    question_id=question.id,
                    point_text="Uses a cache",
                    marks_value=1,
                )
            )
            session.commit()

        self.grader = _FakeGrader()
        self.app = create_app(engine=self.engine, grader=self.grader)
        self.request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/attempts",
                "headers": [],
                "query_string": b"",
                "app": self.app,
            }
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_gemini_grading_validates_json_and_retries_once(self) -> None:
        model = _FakeGeminiModel(
            [
                "not json",
                '```json\n{"points_hit":["Uses a cache"],"points_missed":[],"marks_earned":1,"feedback":"Correct."}\n```',
            ]
        )

        result = grade_answer(
            question_text="Explain cache memory.",
            mark_scheme_points=[{"point_text": "Uses a cache", "marks_value": 1}],
            submitted_answer_text="It stores frequently used data.",
            marks_possible=2,
            model=model,
        )

        self.assertEqual(result.marks_earned, 1)
        self.assertEqual(len(model.prompts), 2)
        self.assertIn("Uses a cache", model.prompts[0])

    def test_subject_and_filtered_question_reads(self) -> None:
        with Session(self.engine) as session:
            subjects = list_subjects(session)
            questions = list_questions(
                subject="9618",
                topic="Data representation",
                command_word="Explain",
                limit=10,
                session=session,
            )

        self.assertEqual(subjects[0].code, "9618")
        self.assertEqual(questions[0].id, 11)

    def test_attempt_is_stored_and_updates_mastery(self) -> None:
        with Session(self.engine) as session:
            result = create_attempt(
                AttemptCreate(
                    user_id=7,
                    question_id=11,
                    submitted_answer_text="It stores frequently used data.",
                ),
                self.request,
                session,
            )

        self.assertEqual(result.marks_earned, 1.0)
        self.assertTrue(result.mastery_updated)
        self.assertEqual(len(self.grader.calls), 1)
        self.assertEqual(
            self.grader.calls[0]["mark_scheme_points"],
            [{"point_text": "Uses a cache", "marks_value": 1}],
        )

        with Session(self.engine) as session:
            mastery = get_mastery(user_id=7, subject="9618", session=session)
        cell = mastery.cells[0]
        self.assertEqual(cell.topic, "Data representation")
        self.assertEqual(cell.command_word, "Explain")
        self.assertEqual(cell.score, 0.5)
        self.assertTrue(cell.has_evidence)

        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(Attempt)).all()), 1)
            self.assertEqual(len(session.scalars(select(Mastery)).all()), 1)

    def test_attempt_rejects_missing_mark_scheme(self) -> None:
        with Session(self.engine) as session:
            question = session.get(Question, 11)
            assert question is not None
            question.mark_scheme_points.clear()
            session.commit()

        with Session(self.engine) as session:
            with self.assertRaises(HTTPException) as raised:
                create_attempt(
                    AttemptCreate(
                        user_id=7,
                        question_id=11,
                        submitted_answer_text="answer",
                    ),
                    self.request,
                    session,
                )
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
